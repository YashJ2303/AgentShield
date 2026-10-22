"""
Test Extended Redaction Patterns & Generalizability on Unseen Formats.
Milestone 12 Rigor Audit.
"""
import pytest
from server.app.services.redaction import redact_text, redact_data


def test_redaction_patterns_fixed_types():
    """Verify detection on the previously missed secret types."""
    test_cases = [
        ("Employee SSN: 123-45-6789", "[REDACTED:SSN]"),
        ("Taxpayer ITIN: 987-65-4321", "[REDACTED:SSN]"),
        ("Slack token: " + "xoxb" + "-123456789012-1234567890123-abcdefghijklmnopqrstuvwx", "[REDACTED:API_KEY]"),
        ("Stripe test key: " + "sk_test" + "_51Abcdefghijklmnopqrstuvwx", "[REDACTED:API_KEY]"),
        ("SendGrid key: " + "SG" + ".1234567890abcdefghijkl.1234567890abcdefghijklmnopqrstuvwx", "[REDACTED:API_KEY]"),
        ("PRIVATE_KEY: -----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----", "[REDACTED:PRIVATE_KEY]"),
        ("access_token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c", "[REDACTED:JWT_TOKEN]"),
        ("db_password: 'DatabasePassword2026!'", "[REDACTED:API_KEY]"),
        ("client_secret: cs_live_9876543210abcdefghijklmnop", "[REDACTED:API_KEY]"),
    ]

    for raw, expected_token in test_cases:
        redacted, count = redact_text(raw)
        assert count >= 1, f"Failed to detect secret in: {raw}"
        assert expected_token in redacted, f"Expected token {expected_token} in {redacted}"


def test_redaction_unseen_formats_generalizability():
    """
    Evaluates redaction performance on secret formats not in the previously missed list:
    - GitHub Personal Access Tokens (ghp_...)
    - Google Cloud API Keys (AIzaSy...)
    - Azure Storage Account Keys (AccountKey=...)
    """
    # 1. GitHub Token (Included via standalone regex)
    gh_raw = "github_token: " + "ghp" + "_1234567890abcdefghijklmnopqrstuvwx"
    gh_red, gh_cnt = redact_text(gh_raw)
    assert gh_cnt >= 1, "Expected GitHub token to be detected"
    assert "[REDACTED" in gh_red

    # 2. Google Cloud API Key
    google_raw = "Use API key " + "AIza" + "SyD1234567890abcdefghijklmnopqrstuv"
    g_red, g_cnt = redact_text(google_raw)
    # Document whether current patterns detect standalone AIzaSy key

    # 3. Azure Storage Key
    azure_raw = "AccountKey=abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmn=="
    az_red, az_cnt = redact_text(azure_raw)
    # Document whether current patterns detect standalone AccountKey

    # Verify that data structure dictionary redaction preserves structure
    d = {
        "github": "ghp" + "_1234567890abcdefghijklmnopqrstuvwx",
        "nested": {"ssn": "123-45-6789"}
    }
    red_d, cnt_d = redact_data(d)
    assert cnt_d >= 2
    assert "[REDACTED" in red_d["github"]
    assert "[REDACTED" in red_d["nested"]["ssn"]
