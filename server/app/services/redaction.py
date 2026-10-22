import re
from typing import Any, Tuple

# Pre-compiled regular expressions
RE_PEM_KEY = re.compile(r"-----BEGIN\s+[A-Z\s]+PRIVATE\s+KEY-----[\s\S]*?(?:-----END\s+[A-Z\s]+PRIVATE\s+KEY-----|\.\.\.)")
RE_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
RE_JWT = re.compile(r"\beyJ[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_.+/=]+\b")
RE_API_KEY = re.compile(
    r"(?i)\b(api[_-]?key|secret(?:[_-]?token)?|password|db[_-]?password|client[_-]?secret|auth[_-]?token|private[_-]?key|access[_-]?token|encryption[_-]?key|aws[_-]?key)\s*[:=]\s*(?:['\"]([^\"'\s]{8,})['\"]|([A-Za-z0-9_\-!@#$%^&*+=]{8,}))"
)
RE_API_KEY_STANDALONE = re.compile(
    r"\b(sk-[A-Za-z0-9_\-]{16,}|sk_(?:test|live)_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9\-]{20,}|SG\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,})\b"
)
RE_SENSITIVE_KEY_NAME = re.compile(r"(?i)^(api[_-]?key|secret|password|auth[_-]?token|private[_-]?key|access[_-]?token)$")
RE_AWS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
RE_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# Fixed email regex (no literal '|' in character class)
RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Credit card candidate pattern (13-19 digits with optional spaces or dashes)
RE_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

# Strict Phone pattern:
# Deliberately conservative to preserve the precision contract in
# tests/test_phone_precision.py (dates, IPs, ports, UUIDs, prices must NOT be redacted).
# Accepted shapes (final subscriber group is 4 digits, as in the "555-01XX" demo range):
#   +1-555-0144, 555-0144, (555) 014-4, +1 555 0144, +1 (555) 123-4567,
#   555-123-4567, 555.123.4567
# The final group is capped at 4 and cannot be followed by more digits, which keeps
# "2026-10-17" and 10-digit numeric IDs from matching.
RE_PHONE = re.compile(
    r"(?<![\w\d:\/])"
    r"(?:\+?\d{1,3}[-.\s])?"           # optional country / area prefix (needs a separator)
    r"(?:\(\d{3}\)|\d{3})[-.\s]"       # 3-digit group, mandatory separator
    r"(?:\d{3}[-.\s])?"                # optional middle group with separator
    r"\d{4}"                           # final group, exactly 4 digits
    r"(?![\w\d:\/])"
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
    """
    Redact secrets and PII from a text string.
    Returns:
        (redacted_text, count_of_redactions)
    """
    if not text or not isinstance(text, str):
        return text, 0

    total_redactions = 0

    # 1. PEM Private Keys
    def _sub_pem(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "[REDACTED:PRIVATE_KEY]"

    text = RE_PEM_KEY.sub(_sub_pem, text)

    # 2. Bearer tokens
    def _sub_bearer(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "Bearer [REDACTED:BEARER_TOKEN]"

    text = RE_BEARER.sub(_sub_bearer, text)

    # 3. Standalone JWTs
    def _sub_jwt(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "[REDACTED:JWT_TOKEN]"

    text = RE_JWT.sub(_sub_jwt, text)

    # 4. API Keys and Secrets (key: value)
    def _sub_api_key(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        key_name = match.group(1)
        return f"{key_name}: [REDACTED:API_KEY]"

    text = RE_API_KEY.sub(_sub_api_key, text)

    # 5. Standalone API Keys (e.g. sk-..., ghp_..., xoxb-..., SG....)
    def _sub_standalone_key(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "[REDACTED:API_KEY]"

    text = RE_API_KEY_STANDALONE.sub(_sub_standalone_key, text)

    # 6. AWS Access Keys
    def _sub_aws(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "[REDACTED:AWS_KEY]"

    text = RE_AWS_KEY.sub(_sub_aws, text)

    # 7. SSN / Tax IDs
    def _sub_ssn(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "[REDACTED:SSN]"

    text = RE_SSN.sub(_sub_ssn, text)

    # 8. Email addresses
    def _sub_email(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "[REDACTED:EMAIL]"

    text = RE_EMAIL.sub(_sub_email, text)

    # 9. Credit Cards with Luhn Check
    def _sub_card(match: re.Match) -> str:
        nonlocal total_redactions
        raw = match.group(0)
        digits_only = re.sub(r"\D", "", raw)
        if luhn_verify(digits_only):
            total_redactions += 1
            return "[REDACTED:CREDIT_CARD]"
        return raw

    text = RE_CARD_CANDIDATE.sub(_sub_card, text)

    # 10. Phone Numbers (strict)
    def _sub_phone(match: re.Match) -> str:
        nonlocal total_redactions
        total_redactions += 1
        return "[REDACTED:PHONE_NUMBER]"

    text = RE_PHONE.sub(_sub_phone, text)

    return text, total_redactions


def redact_data(data: Any) -> Tuple[Any, int]:
    """
    Recursively redact nested structures (dicts, lists, tuples, strings).
    Returns (redacted_data, total_redaction_count).
    """
    if isinstance(data, str):
        return redact_text(data)

    if isinstance(data, dict):
        total = 0
        new_dict = {}
        for k, v in data.items():
            redacted_k, k_count = redact_text(k) if isinstance(k, str) else (k, 0)
            if isinstance(k, str) and RE_SENSITIVE_KEY_NAME.match(k) and isinstance(v, str):
                new_dict[redacted_k] = "[REDACTED:API_KEY]"
                total += (k_count + 1)
            else:
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
