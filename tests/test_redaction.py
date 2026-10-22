import pytest
from server.app.services.redaction import redact_text, redact_data


def test_redact_bearer_tokens():
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-ID"
    redacted, count = redact_text(text)
    assert "Bearer [REDACTED:BEARER_TOKEN]" in redacted
    assert "eyJhbGci" not in redacted
    assert count == 1


def test_redact_api_keys():
    samples = [
        ("api_key: sk-1234567890abcdef123456", "api_key: [REDACTED:API_KEY]"),
        ("secret = 'supersecretkey123456'", "secret: [REDACTED:API_KEY]"),
        ("password: \"mypassword123456789\"", "password: [REDACTED:API_KEY]"),
        ("auth_token: bearer-token-1234567890", "auth_token: [REDACTED:API_KEY]"),
    ]
    for raw, expected_substr in samples:
        redacted, count = redact_text(raw)
        assert "[REDACTED:API_KEY]" in redacted
        assert count == 1


def test_redact_aws_keys():
    text = "Deploying with key AKIAIOSFODNN7EXAMPLE to us-east-1"
    redacted, count = redact_text(text)
    assert "[REDACTED:AWS_KEY]" in redacted
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert count == 1


def test_redact_emails():
    samples = [
        "Reach out to alice@example.com for help.",
        "Internal dev is dev.ops+alert@sub.corp.internal.co.uk.",
    ]
    for s in samples:
        redacted, count = redact_text(s)
        assert "[REDACTED:EMAIL]" in redacted
        assert count == 1


def test_redact_nested_structures():
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant for user@company.com"},
            {"role": "user", "content": "My API key is api_key: secret-key-value-12345678"},
        ],
        "metadata": {
            "credentials": ("admin", "password: strongsecretpass123"),
            "phones": ["555-123-4567"],
            "orders": [{"id": 101, "card": "4532015112830366"}],
        },
    }

    redacted, total_count = redact_data(payload)

    assert total_count == 5
    assert redacted["messages"][0]["content"] == "You are a helpful assistant for [REDACTED:EMAIL]"
    assert "[REDACTED:API_KEY]" in redacted["messages"][1]["content"]
    assert "[REDACTED:API_KEY]" in redacted["metadata"]["credentials"][1]
    assert redacted["metadata"]["phones"][0] == "[REDACTED:PHONE_NUMBER]"
    assert redacted["metadata"]["orders"][0]["card"] == "[REDACTED:CREDIT_CARD]"
    # Non-sensitive fields preserved
    assert redacted["model"] == "gpt-4o"
    assert redacted["metadata"]["orders"][0]["id"] == 101
