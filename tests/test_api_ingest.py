import pytest
import uuid
from datetime import datetime, timezone
from tests.conftest import TEST_API_KEY


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"] == "ok"


def test_api_key_auth(client):
    payload = {
        "task_id": "test-task",
        "spans": [],
    }

    # Missing API key
    resp_no_key = client.post("/ingest/spans", json=payload)
    assert resp_no_key.status_code == 401

    # Invalid API key
    resp_bad_key = client.post(
        "/ingest/spans",
        json=payload,
        headers={"X-API-Key": "completely-invalid-key-xyz"},
    )
    assert resp_bad_key.status_code == 403


def test_batch_ingest_spans_and_run_creation(client):
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "session_id": "session-batch-1",
        "task_id": "analytics-query",
        "prompt_version": "v1.2",
        "model": "gpt-4o",
        "tags": {"environment": "test"},
        "spans": [
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "span_type": "model",
                "name": "gpt-4o",
                "input_payload": {"prompt": "Find customer user@company.com with api_key: secret-key-value-12345678"},
                "output_payload": {"response": "Querying customer database"},
                "started_at": now,
                "ended_at": now,
                "latency_ms": 250,
                "token_counts": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            },
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "span_type": "tool",
                "name": "sql_query",
                "input_payload": {"query": "SELECT * FROM users WHERE email='user@company.com'"},
                "output_payload": {"rows": [{"id": 1, "card": "4532015112830366"}]},
                "started_at": now,
                "ended_at": now,
                "latency_ms": 15,
                "token_counts": {},
            },
        ],
    }

    resp = client.post(
        "/ingest/spans",
        json=payload,
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "ok"
    assert res_data["run_id"] == run_id
    assert res_data["spans_ingested"] == 2
    assert res_data["redaction_count"] > 0

    # Verify run details
    run_resp = client.get(f"/runs/{run_id}")
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["id"] == run_id
    assert run_data["external_session_id"] == "session-batch-1"
    assert run_data["step_count"] == 1
    assert run_data["total_tokens"] == 150
    assert run_data["total_cost"] > 0
    assert len(run_data["spans"]) == 2

    # Verify sensitive data was redacted in stored spans
    tool_span = next(s for s in run_data["spans"] if s["span_type"] == "tool")
    assert "[REDACTED:CREDIT_CARD]" in str(tool_span["output_payload"])
    assert "[REDACTED:EMAIL]" in str(tool_span["input_payload"])


def test_runs_list_search_and_export(client):
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "task_id": "search-unique-task-42",
        "model": "gpt-4o-mini",
        "outcome": "success",
        "spans": [
            {
                "run_id": run_id,
                "span_type": "tool",
                "name": "weather_lookup",
                "input_payload": {"city": "San Francisco"},
                "output_payload": {"temp": 68},
                "started_at": now,
                "ended_at": now,
            }
        ],
    }
    client.post("/ingest/spans", json=payload, headers={"X-API-Key": TEST_API_KEY})

    # 1. Search by task_id keyword
    search_resp = client.get("/runs?search=unique-task-42")
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["total"] >= 1
    assert any(r["id"] == run_id for r in search_data["runs"])

    # 2. Search by tool argument keyword
    arg_search_resp = client.get("/runs?search=San Francisco")
    assert arg_search_resp.status_code == 200
    arg_data = arg_search_resp.json()
    assert any(r["id"] == run_id for r in arg_data["runs"])

    # 3. Export JSON
    json_export = client.get("/runs/export?format=json")
    assert json_export.status_code == 200
    assert json_export.headers["content-type"].startswith("application/json")
    assert run_id in json_export.text

    # 4. Export CSV
    csv_export = client.get("/runs/export?format=csv")
    assert csv_export.status_code == 200
    assert csv_export.headers["content-type"].startswith("text/csv")
    assert "id,external_session_id" in csv_export.text
    assert run_id in csv_export.text
