import pytest
from server.app.services.redaction import luhn_verify, redact_text


def test_luhn_valid_cards():
    # Known valid test card numbers
    valid_cards = [
        "4532015112830366",   # Visa
        "5425233430109903",   # Mastercard
        "378282246310005",    # Amex 15-digits
        "6011111111111117",   # Discover
    ]
    for card in valid_cards:
        assert luhn_verify(card) is True, f"Expected {card} to be valid Luhn"


def test_luhn_invalid_cards():
    invalid_cards = [
        "4532015112830367",   # Bad check digit
        "1234567812345678",   # Random sequence
        "1111111111111111",   # Invalid sum
        "123",                # Too short (<13)
        "123456789012345678901", # Too long (>19)
    ]
    for card in invalid_cards:
        assert luhn_verify(card) is False, f"Expected {card} to be invalid Luhn"


def test_redact_credit_card_integration():
    # Valid card should be redacted
    text_with_valid = "Customer paid with 4532-0151-1283-0366 yesterday."
    redacted, count = redact_text(text_with_valid)
    assert "[REDACTED:CREDIT_CARD]" in redacted
    assert "4532-0151-1283-0366" not in redacted
    assert count == 1

    # Invalid card number should NOT be redacted
    text_with_invalid = "Order reference 1234-5678-1234-5678 was processed."
    redacted_inv, count_inv = redact_text(text_with_invalid)
    assert "[REDACTED:CREDIT_CARD]" not in redacted_inv
    assert "1234-5678-1234-5678" in redacted_inv
    assert count_inv == 0
