import io
import httpx
from pypdf import PdfReader
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.db_models import Document, DocumentChunk


def chunk_text(text: str, chunk_size: int = 700, overlap: int = 120) -> list[str]:
    clean = " ".join(text.split())
    if not clean:
        return []
    chunks = []
    start = 0
    while start < len(clean):
        end = start + chunk_size
        chunks.append(clean[start:end])
        if end >= len(clean):
            break
        start = end - overlap
    return chunks


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Gemini embedding API se 384-dim vectors nikalta hai (batch mein, ultra fast)."""
    if not texts:
        return []
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-embedding-001:batchEmbedContents?key={settings.GEMINI_API_KEY}"
    )
    all_embeddings: list[list[float]] = []

    # Ek baar mein max 20 chunks bhejte hain taaki payload safe rahe
    for i in range(0, len(texts), 20):
        batch = texts[i : i + 20]
        payload = {
            "requests": [
                {
                    "model": "models/gemini-embedding-001",
                    "content": {"parts": [{"text": t}]},
                    "outputDimensionality": 384,
                }
                for t in batch
            ]
        }
        resp = httpx.post(url, json=payload, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        for item in data["embeddings"]:
            all_embeddings.append(item["values"])

    return all_embeddings


def ingest_pdf_document(
    db: Session,
    org_id: str,
    user_id: str,
    filename: str,
    file_bytes: bytes,
    allowed_roles: list[str],
) -> Document:
    reader = PdfReader(io.BytesIO(file_bytes))
    doc = Document(
        org_id=org_id,
        uploaded_by=user_id,
        filename=filename,
        allowed_roles=allowed_roles,
        status="PROCESSING",
        total_pages=len(reader.pages),
    )
    db.add(doc)
    db.flush()

    page_chunks: list[tuple[int, str]] = []
    for page_idx, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        for ch in chunk_text(raw_text):
            page_chunks.append((page_idx, ch))

    if not page_chunks:
        doc.status = "FAILED"
        db.commit()
        return doc

    texts = [c[1] for c in page_chunks]
    vectors = get_embeddings_batch(texts)

    for (page_num, content), vec in zip(page_chunks, vectors):
        chunk_row = DocumentChunk(
            doc_id=doc.id,
            org_id=org_id,
            allowed_roles=allowed_roles,
            page_number=page_num,
            content=content,
            search_vector=func.to_tsvector("english", content),
            embedding=vec,
        )
        db.add(chunk_row)

    doc.status = "READY"
    db.commit()
    db.refresh(doc)
    return doc