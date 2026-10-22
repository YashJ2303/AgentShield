import pytest
from server.app.services.redaction import redact_text


def test_valid_phone_numbers_redacted():
    phones = [
        "Call me at 555-123-4567 now.",
        "Emergency phone: (555) 123-4567.",
        "Contact: +1-555-123-4567 immediately.",
        "Direct line: 555.123.4567 please.",
    ]
    for p in phones:
        redacted, count = redact_text(p)
        assert "[REDACTED:PHONE_NUMBER]" in redacted, f"Failed to redact phone in: {p}"
        assert count == 1


def test_phone_precision_preserves_non_phones():
    non_phones = [
        "Current timestamp is 2026-10-17T12:04:18Z in UTC.",
        "Release scheduled for 2026-10-17 today.",
        "Database is listening on localhost:8080 right now.",
        "Postgres port is 127.0.0.1:5432 in docker.",
        "Run ID is 4589f448-b1e0-4b24-91f8-a25d882c1b8d.",
        "User item id is 123456789.",
        "Product price is 123.45 dollars.",
        "Latency is 45.2 ms per call.",
    ]
    for np in non_phones:
        redacted, count = redact_text(np)
        assert "[REDACTED:PHONE_NUMBER]" not in redacted, f"False positive phone detection on: {np}"
        assert count == 0, f"Expected 0 redactions for '{np}', got {count}"
        assert redacted == np
