import re
import httpx
from app.core.config import settings


def _luhn_check(card_number: str) -> bool:
    digits = [int(d) for d in card_number if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


INJECTION_PATTERNS = [
    r"(ignore|disregard|forget|drop|stop\s+following)\s+(all\s+|your\s+)?(previous|prior|above|earlier|everything|compliance|safety)?\s*(instructions|commands|rules|before\s+this)",
    r"(reveal|print|dump|output|show|leak)\s+(all\s+|me\s+|your\s+)?(the\s+)?(system\s+prompt|hidden\s+instructions|secrets|salaries|passwords|password\s+hash|private\s+tokens|database\s+schema|confidential)",
    r"(bypass|disable|override)\s+(all\s+)?(security|rbac|permissions|rules|pii\s+filtering|system)",
    r"system\s+override",
    r"(you\s+are\s+now|act\s+in|act\s+as|pretend\s+you\s+have)\s+(dan|developer\s+mode|unrestricted|root\s+admin|no\s+safety\s+rules)",
]

SUSPICIOUS_ACTIONS = {"ignore", "disregard", "forget", "bypass", "override", "disable", "pretend", "drop", "leak", "dump", "reveal"}
RESTRICTED_TARGETS = {"rules", "instructions", "commands", "system", "prompt", "secrets", "passwords", "salaries", "tokens", "rbac", "pii", "developer", "root", "confidential", "schema"}


def _check_distilbert_hf(text: str) -> tuple[bool, float]:
    """Tumhare HuggingFace Hub par hosted fine-tuned DistilBERT model ko call karta hai."""
    if not settings.HF_TOKEN or not settings.HF_INJECTION_MODEL:
        return False, 0.0

    url = f"https://router.huggingface.co/hf-inference/models/{settings.HF_INJECTION_MODEL}"
    headers = {"Authorization": f"Bearer {settings.HF_TOKEN}"}
    try:
        resp = httpx.post(url, headers=headers, json={"inputs": text}, timeout=10.0)
        if not resp.is_success:
            return False, 0.0
        data = resp.json()
        items = data[0] if isinstance(data, list) and data and isinstance(data[0], list) else data
        for item in items:
            label = str(item.get("label", "")).upper()
            score = float(item.get("score", 0.0))
            if label in ("INJECTION", "LABEL_1") and score >= 0.75:
                return True, score
    except Exception:
        pass
    return False, 0.0


def detect_prompt_injection(text: str) -> tuple[bool, str | None]:
    lowered = text.lower()

    # Layer 1: Exact Regex Rules
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            return True, f"Blocked by Rule Firewall ({pattern})"

    # Layer 2: Intent-Pair Heuristic Scorer
    words = set(re.findall(r"[a-z]+", lowered))
    if (words & SUSPICIOUS_ACTIONS) and (words & RESTRICTED_TARGETS):
        return True, "Blocked by Intent-Pair Firewall (suspicious action + restricted target)"

    # Layer 3: Fine-tuned DistilBERT ML Classifier
    is_ml_attack, confidence = _check_distilbert_hf(text)
    if is_ml_attack:
        return True, f"Blocked by fine-tuned DistilBERT (confidence: {confidence:.1%})"

    return False, None


def redact_pii(text: str) -> tuple[str, list[str]]:
    entities_found: list[str] = []
    masked = text

    secret_pattern = r"\b(gsk_[A-Za-z0-9]{15,}|AIza[0-9A-Za-z\-_]{20,}|AQ\.[A-Za-z0-9._\-]{20,}|sk-[A-Za-z0-9]{15,})\b"
    if re.search(secret_pattern, masked):
        entities_found.append("API_KEY")
        masked = re.sub(secret_pattern, "<API_KEY_REDACTED>", masked)

    pan_pattern = r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"
    if re.search(pan_pattern, masked):
        entities_found.append("PAN_CARD")
        masked = re.sub(pan_pattern, "<PAN_REDACTED>", masked)

    card_pattern = r"\b(?:\d[ -]*?){13,19}\b"
    def replace_card(match):
        val = match.group(0)
        if _luhn_check(val):
            if "CREDIT_CARD" not in entities_found:
                entities_found.append("CREDIT_CARD")
            return "<CARD_REDACTED>"
        return val
    masked = re.sub(card_pattern, replace_card, masked)

    aadhaar_pattern = r"\b[2-9]{1}[0-9]{3}[\s-]?[0-9]{4}[\s-]?[0-9]{4}\b"
    if re.search(aadhaar_pattern, masked):
        entities_found.append("AADHAAR")
        masked = re.sub(aadhaar_pattern, "<AADHAAR_REDACTED>", masked)

    email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    if re.search(email_pattern, masked):
        entities_found.append("EMAIL")
        masked = re.sub(email_pattern, "<EMAIL_REDACTED>", masked)

    phone_pattern = r"(?:\+91[\s-]?)?\b[6-9]\d{9}\b"
    if re.search(phone_pattern, masked):
        entities_found.append("PHONE")
        masked = re.sub(phone_pattern, "<PHONE_REDACTED>", masked)

    return masked, entities_found