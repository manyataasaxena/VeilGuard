from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.db_models import User, AuditLog

router = APIRouter(prefix="/admin", tags=["FinOps & Security Analytics"])


@router.get("/analytics")
def get_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logs = db.query(AuditLog).filter(AuditLog.org_id == current_user.org_id).all()
    total = len(logs)
    cache_hits = sum(1 for l in logs if l.cache_hit)
    injections_blocked = sum(1 for l in logs if l.injection_blocked)
    pii_events = sum(1 for l in logs if l.pii_entities_found)
    total_tokens = sum(l.tokens_used or 0 for l in logs)
    total_cost = round(sum(l.cost_usd or 0.0 for l in logs), 6)

    non_cached_latencies = [l.latency_ms for l in logs if not l.cache_hit and not l.injection_blocked and l.latency_ms]
    cached_latencies = [l.latency_ms for l in logs if l.cache_hit and l.latency_ms]

    avg_llm_ms = round(sum(non_cached_latencies) / len(non_cached_latencies), 2) if non_cached_latencies else 0.0
    avg_cache_ms = round(sum(cached_latencies) / len(cached_latencies), 2) if cached_latencies else 0.0
    avg_cost_per_call = (total_cost / len(non_cached_latencies)) if non_cached_latencies else 0.00045
    estimated_saved_usd = round(cache_hits * avg_cost_per_call, 6)

    providers: dict[str, int] = {}
    for l in logs:
        providers[l.llm_provider] = providers.get(l.llm_provider, 0) + 1

    return {
        "total_queries": total,
        "cache_hits": cache_hits,
        "cache_hit_rate_pct": round((cache_hits / total) * 100, 1) if total else 0.0,
        "injections_blocked": injections_blocked,
        "pii_redactions": pii_events,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "estimated_cost_saved_usd": estimated_saved_usd,
        "avg_llm_latency_ms": avg_llm_ms,
        "avg_cache_latency_ms": avg_cache_ms,
        "provider_breakdown": providers,
    }


@router.get("/audit-logs")
def get_audit_logs(
    limit: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Only ADMIN can view full audit logs")

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.org_id == current_user.org_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "user_role": r.user_role,
            "query_masked": r.query_masked,
            "pii_entities_found": r.pii_entities_found,
            "injection_blocked": r.injection_blocked,
            "cache_hit": r.cache_hit,
            "llm_provider": r.llm_provider,
            "latency_ms": r.latency_ms,
            "tokens_used": r.tokens_used,
            "cost_usd": r.cost_usd,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]