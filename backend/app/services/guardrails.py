import re


def _luhn_check(card_number: str) -> bool:
    """Credit/Debit card number ko mathematically verify karta hai taaki normal IDs false-flag na hon."""
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
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"reveal\s+(your\s+)?(system\s+prompt|hidden\s+instructions|secrets)",
    r"bypass\s+(security|rbac|permissions|rules)",
    r"you\s+are\s+now\s+(dan|developer\s+mode|unrestricted)",
    r"dump\s+(all\s+)?(database|salaries|passwords|tokens)",
    r"override\s+system",
]


def detect_prompt_injection(text: str) -> tuple[bool, str | None]:
    lowered = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            return True, f"Blocked by injection pattern: {pattern}"
    return False, None


def redact_pii(text: str) -> tuple[str, list[str]]:
    """
    LLM ke paas bhejne se pehle sensitive PII/Secrets ko mask karta hai.
    Returns: (masked_text, list_of_detected_entity_types)
    """
    entities_found: list[str] = []
    masked = text

    # 1. API Keys / Secrets (Groq, Gemini, OpenAI)
    secret_pattern = r"\b(gsk_[A-Za-z0-9]{15,}|AIza[0-9A-Za-z\-_]{20,}|sk-[A-Za-z0-9]{15,})\b"
    if re.search(secret_pattern, masked):
        entities_found.append("API_KEY")
        masked = re.sub(secret_pattern, "<API_KEY_REDACTED>", masked)

    # 2. Indian PAN Card (e.g., ABCDE1234F)
    pan_pattern = r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"
    if re.search(pan_pattern, masked):
        entities_found.append("PAN_CARD")
        masked = re.sub(pan_pattern, "<PAN_REDACTED>", masked)

    # 3. Credit/Debit Cards (with Luhn algorithm verification)
    card_pattern = r"\b(?:\d[ -]*?){13,19}\b"
    def replace_card(match):
        val = match.group(0)
        if _luhn_check(val):
            if "CREDIT_CARD" not in entities_found:
                entities_found.append("CREDIT_CARD")
            return "<CARD_REDACTED>"
        return val
    masked = re.sub(card_pattern, replace_card, masked)

    # 4. Indian Aadhaar (12 digits: xxxx xxxx xxxx)
    aadhaar_pattern = r"\b[2-9]{1}[0-9]{3}[\s-]?[0-9]{4}[\s-]?[0-9]{4}\b"
    if re.search(aadhaar_pattern, masked):
        entities_found.append("AADHAAR")
        masked = re.sub(aadhaar_pattern, "<AADHAAR_REDACTED>", masked)

    # 5. Email Address
    email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    if re.search(email_pattern, masked):
        entities_found.append("EMAIL")
        masked = re.sub(email_pattern, "<EMAIL_REDACTED>", masked)

    # 6. Phone Number (+91 or 10-digit)
    phone_pattern = r"(?:\+91[\s-]?)?\b[6-9]\d{9}\b"
    if re.search(phone_pattern, masked):
        entities_found.append("PHONE")
        masked = re.sub(phone_pattern, "<PHONE_REDACTED>", masked)

    return masked, entities_found