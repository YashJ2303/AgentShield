"""Test that all claims in CLAIMS.md map to valid tests, files, and CSV rows."""

from pathlib import Path
from scripts.check_claims import check_claims


def test_claims_evidence_consistency():
    """Verify that CLAIMS.md contains zero invented tests, missing files, or missing CSV rows."""
    root_dir = Path(__file__).resolve().parent.parent
    assert check_claims(root_dir) is True, "CLAIMS.md failed evidence verification!"
