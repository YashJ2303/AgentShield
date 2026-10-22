import pytest
from fastapi.testclient import TestClient
from server.app.main import app

client = TestClient(app)


def test_eval_file_allowlisted_success():
    """Valid allowlisted files can be read without authorization headers."""
    resp = client.get("/eval-results/file", params={"filename": "CLAIMS.md"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "CLAIMS.md"
    assert "AgentShield: Empirical Claims" in data["content"]
    assert data["size_bytes"] > 0


def test_eval_file_held_out_csv_success():
    resp = client.get("/eval-results/file", params={"filename": "held_out_unsafe_results.csv"})
    assert resp.status_code == 200
    assert "scenario_id" in resp.json()["content"]


def test_eval_file_path_traversal_rejection():
    """Path traversal attempts with slash, backslash, or dot-dot are strictly rejected with 400."""
    bad_filenames = [
        "../etc/passwd",
        "..\\windows\\win.ini",
        "../../eval_results/held_out_unsafe_results.csv",
        "nested/held_out_unsafe_results.csv",
        "..%2F..%2Fsecret",
    ]
    for bad in bad_filenames:
        resp = client.get("/eval-results/file", params={"filename": bad})
        assert resp.status_code == 400, f"Expected 400 for '{bad}', got {resp.status_code}"
        assert "Path traversal detected" in resp.json()["detail"]


def test_eval_file_unallowlisted_rejection():
    """Non-allowlisted file names are rejected with 404."""
    resp = client.get("/eval-results/file", params={"filename": "secret_credentials.env"})
    assert resp.status_code == 404
    assert "not in the evaluation allowlist" in resp.json()["detail"]


def test_eval_held_out_scenarios_structured_endpoint():
    """Structured held-out scenarios endpoint parses CSV into JSON records."""
    resp = client.get("/eval-results/held-out")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) > 0
    first = items[0]
    assert "scenario_id" in first
    assert "agent_type" in first
    assert "blocked_by_policy" in first


def test_eval_study_overview_structured_endpoint():
    """Structured study overview endpoint parses results and reports."""
    resp = client.get("/eval-results/study-overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "available_files" in data
    assert "CLAIMS.md" in data["available_files"]


def test_eval_endpoint_refuses_directory_listing_and_directory_traversal():
    """
    Proves that the eval-results endpoint refuses path traversal and serves only
    fixed allowed filenames, never directory listings or non-allowlisted directories.
    """
    # 1. Prohibit directory paths
    directory_queries = [".", "..", "eval_results", "server", "eval_results/", "/eval_results"]
    for dir_query in directory_queries:
        resp = client.get("/eval-results/file", params={"filename": dir_query})
        assert resp.status_code in (400, 404)

    # 2. Verify root /eval-results does NOT list directory contents
    resp_root = client.get("/eval-results")
    assert resp_root.status_code == 404

    # 3. Verify /eval-results/file without filename parameter fails validation
    resp_empty = client.get("/eval-results/file")
    assert resp_empty.status_code == 422


def test_eval_replay_variants_structured_endpoint():
    """Verify 50 replay regression variants are served with composite fidelity scores."""
    resp = client.get("/eval-results/replay-variants")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 50
    assert any(r["variant_id"] == "test_ben_04" for r in rows)
    assert any(r["variant_id"] == "test_ben_11" for r in rows)


