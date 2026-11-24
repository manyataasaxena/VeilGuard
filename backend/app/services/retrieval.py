import re
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.db_models import Document, DocumentChunk
from app.services.ingestion import get_embeddings_batch


def _stage2_rerank_score(query: str, content: str, rrf_score: float) -> float:
    """Stage-2 lightweight lexical + phrase coverage reranker."""
    q_terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
    if not q_terms:
        return rrf_score
    c_lower = content.lower()
    hits = sum(1 for t in q_terms if t in c_lower)
    coverage = hits / len(q_terms)
    return rrf_score + (0.015 * coverage)


def hybrid_rbac_search(
    db: Session,
    org_id: str,
    user_role: str,
    query: str,
    top_k: int = 4,
) -> list[dict]:
    query_vec = get_embeddings_batch([query])[0]

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

    # Stage-2 Reranking + Duplicate Content Removal
    for item in rrf_scores.values():
        item["rerank_score"] = _stage2_rerank_score(query, item["content"], item["rrf_score"])

    sorted_items = sorted(rrf_scores.values(), key=lambda x: x["rerank_score"], reverse=True)

    deduped = []
    seen_prefixes = set()
    for item in sorted_items:
        prefix = item["content"][:100].strip()
        if prefix not in seen_prefixes:
            seen_prefixes.add(prefix)
            deduped.append(item)
        if len(deduped) >= top_k:
            break

    return deduped