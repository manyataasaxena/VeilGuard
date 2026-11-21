from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.db_models import Document, DocumentChunk
from app.services.ingestion import get_embeddings_batch


def hybrid_rbac_search(
    db: Session,
    org_id: str,
    user_role: str,
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """
    Zero-Leakage Hybrid Search:
    1) Database query ke andar hi org_id + user_role filter lagta hai.
    2) Vector search (pgvector) + Keyword search (TSVECTOR) ko RRF se merge karta hai.
    """
    query_vec = get_embeddings_batch([query])[0]

    # 1. Dense Vector Search (Top 15) — strictly RBAC filtered
    vec_rows = (
        db.query(
            DocumentChunk,
            Document.filename,
            DocumentChunk.embedding.cosine_distance(query_vec).label("distance"),
        )
        .join(Document, DocumentChunk.doc_id == Document.id)
        .filter(
            DocumentChunk.org_id == org_id,
            DocumentChunk.allowed_roles.any(user_role),
        )
        .order_by("distance")
        .limit(15)
        .all()
    )

    # 2. Keyword Full-Text Search (Top 15) — strictly RBAC filtered
    ts_query = func.plainto_tsquery("english", query)
    kw_rows = (
        db.query(
            DocumentChunk,
            Document.filename,
            func.ts_rank(DocumentChunk.search_vector, ts_query).label("rank_score"),
        )
        .join(Document, DocumentChunk.doc_id == Document.id)
        .filter(
            DocumentChunk.org_id == org_id,
            DocumentChunk.allowed_roles.any(user_role),
            DocumentChunk.search_vector.op("@@")(ts_query),
        )
        .order_by(func.ts_rank(DocumentChunk.search_vector, ts_query).desc())
        .limit(15)
        .all()
    )

    # 3. Reciprocal Rank Fusion (RRF) — dono rankings ko combine karo
    rrf_scores: dict[str, dict] = {}
    k = 60

    for rank, (chunk, fname, dist) in enumerate(vec_rows, start=1):
        rrf_scores[chunk.id] = {
            "chunk_id": chunk.id,
            "filename": fname,
            "page_number": chunk.page_number,
            "content": chunk.content,
            "allowed_roles": chunk.allowed_roles,
            "rrf_score": 1.0 / (k + rank),
            "vector_similarity": round(1 - float(dist), 4),
        }

    for rank, (chunk, fname, _) in enumerate(kw_rows, start=1):
        if chunk.id not in rrf_scores:
            rrf_scores[chunk.id] = {
                "chunk_id": chunk.id,
                "filename": fname,
                "page_number": chunk.page_number,
                "content": chunk.content,
                "allowed_roles": chunk.allowed_roles,
                "rrf_score": 0.0,
                "vector_similarity": 0.0,
            }
        rrf_scores[chunk.id]["rrf_score"] += 1.0 / (k + rank)

    ranked = sorted(rrf_scores.values(), key=lambda x: x["rrf_score"], reverse=True)
    return ranked[:top_k]