import hashlib
import json
import math
import re
import time
from collections import Counter
from fastapi import HTTPException
from app.core.database import redis_client

RATE_CAPACITY = 15.0        # Burst limit: max 15 requests
RATE_REFILL_PER_SEC = 0.5   # Har 2 second mein 1 token refill


def check_rate_limit(user_id: str) -> None:
    """Redis Token-Bucket Rate Limiter."""
    key = f"veilguard:ratelimit:{user_id}"
    now = time.time()
    data = redis_client.hgetall(key)

    if not data:
        tokens = RATE_CAPACITY - 1.0
        redis_client.hset(key, mapping={"tokens": str(tokens), "last_ts": str(now)})
        redis_client.expire(key, 120)
        return

    tokens = float(data.get("tokens", RATE_CAPACITY))
    last_ts = float(data.get("last_ts", now))
    elapsed = max(0.0, now - last_ts)
    tokens = min(RATE_CAPACITY, tokens + elapsed * RATE_REFILL_PER_SEC)

    if tokens < 1.0:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded (Token Bucket empty). Please wait a few seconds.",
        )

    tokens -= 1.0
    redis_client.hset(key, mapping={"tokens": str(tokens), "last_ts": str(now)})
    redis_client.expire(key, 120)


def _normalize(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return " ".join(cleaned.split())


def _ngram_cosine(q1: str, q2: str) -> float:
    """Fast local unigram+bigram cosine similarity (<1ms, zero external API call)."""
    def features(s: str) -> Counter:
        words = _normalize(s).split()
        bigrams = [f"{words[i]}_{words[i+1]}" for i in range(len(words) - 1)]
        return Counter(words + bigrams)

    v1, v2 = features(q1), features(q2)
    if not v1 or not v2:
        return 0.0
    common = set(v1.keys()) & set(v2.keys())
    dot = sum(v1[k] * v2[k] for k in common)
    mag1 = math.sqrt(sum(v * v for v in v1.values()))
    mag2 = math.sqrt(sum(v * v for v in v2.values()))
    return dot / (mag1 * mag2) if mag1 and mag2 else 0.0


def get_cached_response(org_id: str, role: str, masked_query: str) -> dict | None:
    norm = _normalize(masked_query)
    q_hash = hashlib.sha256(norm.encode()).hexdigest()[:16]
    exact_key = f"veilguard:cache:exact:{org_id}:{role}:{q_hash}"

    # Tier 1: Exact normalized O(1) lookup
    raw = redis_client.get(exact_key)
    if raw:
        return json.loads(raw)

    # Tier 2: Similar paraphrase lookup across recent role-scoped queries
    bucket_key = f"veilguard:cache:bucket:{org_id}:{role}"
    recent_items = redis_client.lrange(bucket_key, 0, 24)
    for item_str in recent_items:
        item = json.loads(item_str)
        if _ngram_cosine(masked_query, item["query_masked"]) >= 0.78:
            return item["response"]

    return None


def set_cached_response(org_id: str, role: str, masked_query: str, response_data: dict) -> None:
    norm = _normalize(masked_query)
    q_hash = hashlib.sha256(norm.encode()).hexdigest()[:16]
    exact_key = f"veilguard:cache:exact:{org_id}:{role}:{q_hash}"
    bucket_key = f"veilguard:cache:bucket:{org_id}:{role}"

    redis_client.setex(exact_key, 1800, json.dumps(response_data))  # 30 min TTL
    bucket_entry = json.dumps({"query_masked": masked_query, "response": response_data})
    redis_client.lpush(bucket_key, bucket_entry)
    redis_client.ltrim(bucket_key, 0, 24)
    redis_client.expire(bucket_key, 1800)