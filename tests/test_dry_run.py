import pytest
import uuid
from datetime import datetime, timezone
from server.app.config import settings
from tests.conftest import TEST_API_KEY


@pytest.fixture
def seed_historical_runs_and_spans(client):
    """Seed runs and spans with known original decisions for dry-run simulation."""
    now = datetime.now(timezone.utc).isoformat()
    run_1_id = str(uuid.uuid4())
    run_2_id = str(uuid.uuid4())

    # Ingest Run 1: 2 allowed tool calls
    client.post(
        "/ingest/spans",
        headers={"X-API-Key": TEST_API_KEY},
        json={
            "session_id": "sess-dry-1",
            "task_id": "task-research",
            "spans": [
                {
                    "id": str(uuid.uuid4()),
                    "run_id": run_1_id,
                    "sequence_number": 1,
                    "span_type": "tool",
                    "name": "web_search",
                    "input_payload": {"query": "deep learning"},
                    "output_payload": {"results": ["url1", "url2"]},
                    "policy_decision": "allow",
                    "policy_rule_id": "rule_allow_search",
                    "started_at": now,
                    "ended_at": now,
                },
                {
                    "id": str(uuid.uuid4()),
                    "run_id": run_1_id,
                    "sequence_number": 2,
                    "span_type": "tool",
                    "name": "file_write",
                    "input_payload": {"path": "./sandbox/out.txt", "data": "hello"},
                    "output_payload": {"bytes": 5},
                    "policy_decision": "allow",
                    "policy_rule_id": "rule_allow_sandbox_write",
                    "started_at": now,
                    "ended_at": now,
                },
            ],
        },
    )

    # Ingest Run 2: 1 allowed tool call and 1 denied tool call
    client.post(
        "/ingest/spans",
        headers={"X-API-Key": TEST_API_KEY},
        json={
            "session_id": "sess-dry-2",
            "task_id": "task-maintenance",
            "spans": [
                {
                    "id": str(uuid.uuid4()),
                    "run_id": run_2_id,
                    "sequence_number": 1,
                    "span_type": "tool",
                    "name": "sql_query",
                    "input_payload": {"query": "SELECT count(*) FROM users WHERE id > 0;"},
                    "output_payload": {"count": 42},
                    "policy_decision": "allow",
                    "policy_rule_id": "rule_allow_sql",
                    "started_at": now,
                    "ended_at": now,
                },
                {
                    "id": str(uuid.uuid4()),
                    "run_id": run_2_id,
                    "sequence_number": 2,
                    "span_type": "tool",
                    "name": "bash_exec",
                    "input_payload": {"cmd": "rm -rf /"},
                    "output_payload": {"error": "Blocked"},
                    "policy_decision": "deny",
                    "policy_rule_id": "rule_block_bash",
                    "started_at": now,
                    "ended_at": now,
                },
            ],
        },
    )

    return run_1_id, run_2_id


def test_dry_run_simulation_and_diffs(client, seed_historical_runs_and_spans):
    """
    Test evaluating a candidate policy against historical runs.
    Candidate policy denies file_write (which was allowed in history).
    Verifies that diffs accurately flag has_changed=True.
    """
    run_1_id, run_2_id = seed_historical_runs_and_spans

    # Candidate policy: allows search and SQL, but strictly denies file_write
    candidate_yaml = """
version: 2
default_action: deny
rules:
  - id: candidate_allow_search
    tool: web_search
    action: allow
  - id: candidate_deny_file_write
    tool: file_write
    action: deny
  - id: candidate_allow_sql
    tool: sql_query
    action: allow
    sql_check:
      arg: query
      allowed_operations: [SELECT]
"""

    resp = client.post(
        "/policies/dry-run",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={
            "candidate_yaml": candidate_yaml,
            "run_ids": [run_1_id, run_2_id],
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_runs_evaluated"] == 2
    assert data["total_spans_evaluated"] == 4
    # Expected candidate decisions:
    # web_search: allow
    # file_write: deny (CHANGED from original allow)
    # sql_query: allow
    # bash_exec: deny (default action deny)
    assert data["would_allow"] == 2
    assert data["would_deny"] == 2
    assert data["would_require_approval"] == 0

    # Exactly 1 span changed its verdict (file_write was allow, now deny)
    assert data["changed_count"] == 1

    file_write_diff = next(d for d in data["diffs"] if d["tool_name"] == "file_write")
    assert file_write_diff["original_decision"] == "allow"
    assert file_write_diff["candidate_decision"] == "deny"
    assert file_write_diff["has_changed"] is True
    assert file_write_diff["candidate_rule_id"] == "candidate_deny_file_write"


def test_dry_run_against_stored_policy_version(client, seed_historical_runs_and_spans):
    """Test dry-run simulation using an uploaded policy version number."""
    run_1_id, run_2_id = seed_historical_runs_and_spans

    # Upload policy version
    upload_resp = client.post(
        "/policies",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={
            "yaml_content": "version: 99\ndefault_action: allow\nrules: []\n",
            "change_note": "Allow all test version",
        },
    )
    assert upload_resp.status_code == 201
    version_num = upload_resp.json()["version_number"]

    # Run dry-run referencing version_number
    resp = client.post(
        "/policies/dry-run",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={
            "candidate_version_number": version_num,
            "run_ids": [run_1_id],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_runs_evaluated"] == 1
    assert data["total_spans_evaluated"] == 2
    assert data["would_allow"] == 2


def test_dry_run_validation_errors(client):
    """Test that invalid YAML syntax fails closed with 422 Unprocessable Content."""
    # 1. Broken YAML syntax
    resp_syntax = client.post(
        "/policies/dry-run",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={"candidate_yaml": "version: 1\nrules: [broken yaml:"},
    )
    assert resp_syntax.status_code == 422
    assert "Candidate policy validation failed" in resp_syntax.json()["detail"]

    # 2. Missing both YAML and version number
    resp_empty = client.post(
        "/policies/dry-run",
        headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        json={},
    )
    assert resp_empty.status_code == 400
    assert "Either candidate_yaml or candidate_version_number must be provided" in resp_empty.json()["detail"]


def test_dry_run_admin_token_required(client):
    """Verify dry-run simulation requires valid admin token."""
    resp = client.post(
        "/policies/dry-run",
        headers={"X-Admin-Token": "invalid-token"},
        json={"candidate_yaml": "version: 1\ndefault_action: deny\nrules: []\n"},
    )
    assert resp.status_code == 403
    assert "Invalid or missing X-Admin-Token" in resp.json()["detail"]
