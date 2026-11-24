import httpx
from app.core.config import settings
from app.core.database import redis_client

CIRCUIT_KEY = "veilguard:circuit:groq_open"
GROQ_MODEL_CACHE_KEY = "veilguard:groq:active_model"


def build_grounded_prompt(query: str, chunks: list[dict]) -> str:
    context_blocks = []
    for idx, ch in enumerate(chunks, start=1):
        context_blocks.append(
            f"[Source {idx}: {ch['filename']}, Page {ch['page_number']}]\n{ch['content']}"
        )
    context_str = "\n\n---\n\n".join(context_blocks)

    return (
        "You are VeilGuard, a strict enterprise compliance AI assistant.\n"
        "RULES:\n"
        "1. Answer ONLY using the verified context provided below.\n"
        "2. Always cite sources inline like [Source: filename, Page X].\n"
        "3. If the context does not contain enough information, clearly state: "
        "'Insufficient verified context in authorized documents.'\n"
        "4. Never invent numbers, clauses, or policies.\n\n"
        f"VERIFIED CONTEXT:\n{context_str}\n\n"
        f"USER QUESTION: {query}"
    )


def _get_active_groq_model() -> str:
    cached = redis_client.get(GROQ_MODEL_CACHE_KEY)
    if cached:
        return cached

    resp = httpx.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
        timeout=15.0,
    )
    resp.raise_for_status()
    models = [m["id"] for m in resp.json().get("data", [])]

    excluded = ("whisper", "tts", "guard", "orpheus", "playai")
    chat_models = [m for m in models if not any(bad in m.lower() for bad in excluded)]

    preferred = [
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3-32b",
    ]
    chosen = next((p for p in preferred if p in chat_models), None)
    if not chosen:
        if not chat_models:
            raise RuntimeError(f"No chat models found on Groq: {models}")
        chosen = chat_models[0]

    redis_client.setex(GROQ_MODEL_CACHE_KEY, 3600, chosen)
    return chosen


def _call_groq(prompt: str) -> tuple[str, int, str]:
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not configured")

    model_id = _get_active_groq_model()
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 600,
    }
    resp = httpx.post(url, headers=headers, json=payload, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    answer = data["choices"][0]["message"]["content"]
    tokens = data.get("usage", {}).get("total_tokens", 0)
    return answer, tokens, f"groq/{model_id}"


def _call_gemini(prompt: str) -> tuple[str, int, str]:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not configured")

    headers = {
        "x-goog-api-key": settings.GEMINI_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 600},
    }

    candidates = [
        "gemini-2.5-flash-lite",
        "gemini-flash-latest",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite-preview",
    ]
    last_err = None
    for model_name in candidates:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=30.0)
            if resp.status_code in (400, 404):
                last_err = resp.text
                continue
            resp.raise_for_status()
            data = resp.json()
            answer = data["candidates"][0]["content"]["parts"][0]["text"]
            tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)
            return answer, tokens, f"gemini/{model_name}"
        except httpx.TimeoutException as e:
            last_err = str(e)
            continue

    raise RuntimeError(f"All Gemini models failed: {last_err}")


def generate_with_circuit_breaker(query: str, chunks: list[dict], force_primary_fail: bool = False) -> dict:
    prompt = build_grounded_prompt(query, chunks)
    groq_open = redis_client.get(CIRCUIT_KEY) == "1"
    failover_triggered = False

    if not groq_open and not force_primary_fail:
        try:
            answer, tokens, provider = _call_groq(prompt)
            cost_usd = round((tokens / 1_000_000) * 0.59, 6)
            return {
                "answer": answer,
                "tokens_used": tokens,
                "provider": provider,
                "cost_usd": cost_usd,
                "failover_triggered": False,
            }
        except Exception as e:
            print(f"[Circuit Breaker] Groq failed -> switching to Gemini: {e}")
            redis_client.setex(CIRCUIT_KEY, 60, "1")
            failover_triggered = True
    else:
        failover_triggered = True

    answer, tokens, provider = _call_gemini(prompt)
    cost_usd = round((tokens / 1_000_000) * 0.15, 6)
    return {
        "answer": answer,
        "tokens_used": tokens,
        "provider": provider,
        "cost_usd": cost_usd,
        "failover_triggered": failover_triggered,
    }