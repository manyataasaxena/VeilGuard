import time
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.db_models import User, AuditLog
from app.services.guardrails import detect_prompt_injection, redact_pii
from app.services.retrieval import hybrid_rbac_search
from app.services.llm_gateway import generate_with_circuit_breaker
from app.services.cache import check_rate_limit, get_cached_response, set_cached_response

router = APIRouter(prefix="/chat", tags=["Zero-Trust AI Chat Gateway"])


class ChatRequest(BaseModel):
    query: str
    simulate_failover: bool = False


def _run_zero_trust_pipeline(req: ChatRequest, current_user: User, db: Session) -> dict:
    total_start = time.perf_counter()

    # 0. Redis Token-Bucket Rate Limiter
    check_rate_limit(current_user.id)

    # 1. Prompt Injection Firewall
    t0 = time.perf_counter()
    is_injection, reason = detect_prompt_injection(req.query)
    injection_ms = round((time.perf_counter() - t0) * 1000, 2)

    # 2. PII & Secret Redaction
    t1 = time.perf_counter()
    masked_query, pii_found = redact_pii(req.query)
    pii_ms = round((time.perf_counter() - t1) * 1000, 2)

    if is_injection:
        total_ms = round((time.perf_counter() - total_start) * 1000, 2)
        db.add(AuditLog(
            org_id=current_user.org_id,
            user_id=current_user.id,
            user_role=current_user.role,
            query_masked=masked_query,
            pii_entities_found=pii_found,
            injection_blocked=True,
            llm_provider="blocked_by_firewall",
            latency_ms=total_ms,
        ))
        db.commit()
        raise HTTPException(
            status_code=403,
            detail={"error": "Prompt injection attempt blocked by VeilGuard Firewall", "reason": reason},
        )

    # 3. Redis Semantic Cache Check (Skip if simulate_failover is True)
    t_cache = time.perf_counter()
    cached = None if req.simulate_failover else get_cached_response(
        current_user.org_id, current_user.role, masked_query
    )
    cache_ms = round((time.perf_counter() - t_cache) * 1000, 2)

    if cached:
        total_ms = round((time.perf_counter() - total_start) * 1000, 2)
        db.add(AuditLog(
            org_id=current_user.org_id,
            user_id=current_user.id,
            user_role=current_user.role,
            query_masked=masked_query,
            pii_entities_found=pii_found,
            cache_hit=True,
            llm_provider="redis_semantic_cache",
            latency_ms=total_ms,
            tokens_used=0,
            cost_usd=0.0,
        ))
        db.commit()
        cached_resp = dict(cached)
        cached_resp["cache_hit"] = True
        cached_resp["pii_redacted"] = pii_found
        cached_resp["provider"] = "redis_semantic_cache"
        cached_resp["tokens_used"] = 0
        cached_resp["cost_usd"] = 0.0
        cached_resp["latency_waterfall_ms"] = {
            "injection_check": injection_ms,
            "pii_redaction": pii_ms,
            "semantic_cache_lookup": cache_ms,
            "hybrid_rbac_retrieval": 0.0,
            "llm_inference": 0.0,
            "total": total_ms,
        }
        return cached_resp

    # 4. Zero-Leakage Hybrid RBAC Search + Stage-2 Reranking
    t2 = time.perf_counter()
    chunks = hybrid_rbac_search(
        db=db,
        org_id=current_user.org_id,
        user_role=current_user.role,
        query=masked_query,
        top_k=4,
    )
    retrieval_ms = round((time.perf_counter() - t2) * 1000, 2)

    if not chunks:
        total_ms = round((time.perf_counter() - total_start) * 1000, 2)
        db.add(AuditLog(
            org_id=current_user.org_id,
            user_id=current_user.id,
            user_role=current_user.role,
            query_masked=masked_query,
            pii_entities_found=pii_found,
            llm_provider="none_rbac_no_match",
            latency_ms=total_ms,
        ))
        db.commit()
        return {
            "answer": f"Insufficient verified context for your role ({current_user.role}). No authorized documents matched this query.",
            "query_masked": masked_query,
            "pii_redacted": pii_found,
            "cache_hit": False,
            "citations": [],
            "provider": "none",
            "failover_triggered": False,
            "tokens_used": 0,
            "cost_usd": 0.0,
            "latency_waterfall_ms": {
                "injection_check": injection_ms,
                "pii_redaction": pii_ms,
                "semantic_cache_lookup": cache_ms,
                "hybrid_rbac_retrieval": retrieval_ms,
                "llm_inference": 0.0,
                "total": total_ms,
            },
        }

    # 5. Resilient LLM Generation (Groq -> Gemini Circuit Breaker)
    t3 = time.perf_counter()
    llm_res = generate_with_circuit_breaker(
        query=masked_query,
        chunks=chunks,
        force_primary_fail=req.simulate_failover,
    )
    llm_ms = round((time.perf_counter() - t3) * 1000, 2)
    total_ms = round((time.perf_counter() - total_start) * 1000, 2)

    # 6. Audit Log Save
    db.add(AuditLog(
        org_id=current_user.org_id,
        user_id=current_user.id,
        user_role=current_user.role,
        query_masked=masked_query,
        pii_entities_found=pii_found,
        injection_blocked=False,
        cache_hit=False,
        llm_provider=llm_res["provider"],
        latency_ms=total_ms,
        tokens_used=llm_res["tokens_used"],
        cost_usd=llm_res["cost_usd"],
    ))
    db.commit()

    citations = [
        {
            "filename": c["filename"],
            "page_number": c["page_number"],
            "snippet": c["content"][:220] + "...",
            "rrf_score": round(c["rrf_score"], 5),
        }
        for c in chunks
    ]

    response_payload = {
        "answer": llm_res["answer"],
        "query_masked": masked_query,
        "pii_redacted": pii_found,
        "cache_hit": False,
        "citations": citations,
        "provider": llm_res["provider"],
        "failover_triggered": llm_res["failover_triggered"],
        "tokens_used": llm_res["tokens_used"],
        "cost_usd": llm_res["cost_usd"],
        "latency_waterfall_ms": {
            "injection_check": injection_ms,
            "pii_redaction": pii_ms,
            "semantic_cache_lookup": cache_ms,
            "hybrid_rbac_retrieval": retrieval_ms,
            "llm_inference": llm_ms,
            "total": total_ms,
        },
    }

    # Cache valid response in Redis (skip if failover was simulated)
    if not req.simulate_failover:
        set_cached_response(current_user.org_id, current_user.role, masked_query, response_payload)

    return response_payload


@router.post("/ask")
def ask_chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _run_zero_trust_pipeline(req, current_user, db)


@router.post("/stream")
async def stream_chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = _run_zero_trust_pipeline(req, current_user, db)

    async def event_generator():
        words = result["answer"].split(" ")
        for w in words:
            yield f"data: {json.dumps({'type': 'token', 'content': w + ' '})}\n\n"
            await asyncio.sleep(0.02)
        meta = {k: v for k, v in result.items() if k != "answer"}
        yield f"data: {json.dumps({'type': 'meta', 'data': meta})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")