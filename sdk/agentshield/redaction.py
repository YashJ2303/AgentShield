import re
from typing import Any, Tuple

RE_PEM_KEY = re.compile(r"-----BEGIN\s+[A-Z\s]+PRIVATE\s+KEY-----[\s\S]*?(?:-----END\s+[A-Z\s]+PRIVATE\s+KEY-----|\.\.\.)")
RE_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
RE_JWT = re.compile(r"\beyJ[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_.+/=]+\b")
RE_API_KEY = re.compile(
    r"(?i)\b(api[_-]?key|secret(?:[_-]?token)?|password|db[_-]?password|client[_-]?secret|auth[_-]?token|private[_-]?key|access[_-]?token|encryption[_-]?key|aws[_-]?key)\s*[:=]\s*(?:['\"]([^\"'\s]{8,})['\"]|([A-Za-z0-9_\-!@#$%^&*+=]{8,}))"
)
RE_API_KEY_STANDALONE = re.compile(
    r"\b(sk-[A-Za-z0-9_\-]{16,}|sk_(?:test|live)_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9\-]{20,}|SG\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,})\b"
)
RE_AWS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
RE_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
RE_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
RE_PHONE = re.compile(
    r"(?<![\w\d:\/])(?:\+?[1-9]\d{0,2}[-.\s]?)?(?:\(?\d{3}\)?[-.\s])\d{3}[-.\s]\d{4}(?![\w\d:\/])"
)



def luhn_verify(number_str: str) -> bool:
    """Validate a credit card candidate string using the Luhn algorithm."""
    digits = [int(c) for c in number_str if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    
    checksum = 0
    reverse_digits = digits[::-1]
    for i, digit in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = digit * 2
            checksum += (doubled - 9) if doubled > 9 else doubled
        else:
            checksum += digit
    return checksum % 10 == 0


def redact_text(text: str) -> Tuple[str, int]:
    """Redact secrets and PII from a text string."""
    if not text or not isinstance(text, str):
        return text, 0

    total_redactions = 0

    def _sub_pem(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "[REDACTED:PRIVATE_KEY]"

    text = RE_PEM_KEY.sub(_sub_pem, text)

    def _sub_bearer(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "Bearer [REDACTED:BEARER_TOKEN]"

    text = RE_BEARER.sub(_sub_bearer, text)

    def _sub_jwt(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "[REDACTED:JWT_TOKEN]"

    text = RE_JWT.sub(_sub_jwt, text)

    def _sub_api_key(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        key_name = match.group(1)
        return f"{key_name}: [REDACTED:API_KEY]"

    text = RE_API_KEY.sub(_sub_api_key, text)

    def _sub_standalone_key(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "[REDACTED:API_KEY]"

    text = RE_API_KEY_STANDALONE.sub(_sub_standalone_key, text)

    def _sub_aws(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "[REDACTED:AWS_KEY]"

    text = RE_AWS_KEY.sub(_sub_aws, text)

    def _sub_ssn(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "[REDACTED:SSN]"

    text = RE_SSN.sub(_sub_ssn, text)

    def _sub_email(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "[REDACTED:EMAIL]"

    text = RE_EMAIL.sub(_sub_email, text)

    def _sub_card(match: re.Match) -> str:
        nonlocal total_redactions
        raw = match.group(0)
        digits_only = re.sub(r"\D", "", raw)
        if luhn_verify(digits_only):
            total_redactions += 1
            return "[REDACTED:CREDIT_CARD]"
        return raw

    text = RE_CARD_CANDIDATE.sub(_sub_card, text)

    def _sub_phone(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "[REDACTED:PHONE_NUMBER]"

    text = RE_PHONE.sub(_sub_phone, text)

    return text, total_redactions


def redact_data(data: Any) -> Tuple[Any, int]:
    """Recursively redact nested dictionaries, lists, and strings."""
    if isinstance(data, str):
        return redact_text(data)

    if isinstance(data, dict):
        total = 0
        new_dict = {}
        for k, v in data.items():
            redacted_k, k_count = redact_text(k) if isinstance(k, str) else (k, 0)
            redacted_v, v_count = redact_data(v)
            new_dict[redacted_k] = redacted_v
            total += (k_count + v_count)
        return new_dict, total

    if isinstance(data, list):
        total = 0
        new_list = []
        for item in data:
            redacted_item, count = redact_data(item)
            new_list.append(redacted_item)
            total += count
        return new_list, total

    if isinstance(data, tuple):
        total = 0
        new_items = []
        for item in data:
            redacted_item, count = redact_data(item)
            new_items.append(redacted_item)
            total += count
        return tuple(new_items), total

    return data, 0
