"""
Test Real End-to-End Latency Instrumentation.
Milestone 12 Rigor Audit.
"""
import pytest
import time
from sdk.agentshield.client import GatewayClient, GatewayConfig
from server.app.services.redaction import redact_text
from evaluation.agents.sql_agent import SqlAgent
from tests.conftest import TEST_API_KEY


def test_full_instrumented_tool_call_pipeline(client, db_session):
    """
    Verifies that the full instrumented tool call pipeline functions end-to-end:
    1. Pre-call Gateway check via HTTP POST /gateway/check
    2. Real database tool execution (SQLite)
    3. Output screening & redaction
    4. Post-call telemetry span ingest
    """
    # 1. Activate default policy via TestClient
    with open("policies/default_policy.yaml", "r") as f:
        policy_yaml = f.read()

    resp = client.post(
        "/policies",
        json={"yaml_content": policy_yaml, "change_note": "Activated benchmark policy"},
        headers={"X-Admin-Token": "test-admin-secret"},
    )
    assert resp.status_code == 201

    # 2. Configure GatewayClient to route through TestClient
    gw_client = GatewayClient(
        config=GatewayConfig(
            server_url="http://testserver",
            api_key=TEST_API_KEY,
            http_client=client,
        )
    )

    db_path, conn = SqlAgent.create_fresh_database()
    cursor = conn.cursor()

    query = "SELECT count(*) FROM users WHERE role = 'analyst';"

    # Pipeline measurement
    t0 = time.perf_counter()

    # Pre-call Check
    check_resp = gw_client.check_tool(
        run_id="run_bench_01",
        tool_name="sql_query",
        tool_args={"query": query},
    )
    assert check_resp["decision"] == "allow"

    # Execution
    cursor.execute(query)
    rows = cursor.fetchall()
    output_str = str(rows)

    # Output screening
    redacted_out, red_cnt = redact_text(output_str)

    # Post-call Telemetry Span Ingest
    import uuid
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    ingest_resp = client.post(
        "/ingest/spans",
        json={
            "task_id": "benchmark_task",
            "spans": [
                {
                    "id": str(uuid.uuid4()),
                    "run_id": "run_bench_01",
                    "span_type": "tool",
                    "name": "sql_query",
                    "input_payload": {"query": query},
                    "output_payload": {"result": redacted_out},
                    "started_at": now_iso,
                    "ended_at": now_iso,
                    "latency_ms": 2,
                }
            ]
        },
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert ingest_resp.status_code == 200

    t_end = time.perf_counter()
    duration_ms = (t_end - t0) * 1000.0

    assert duration_ms > 0.0
    assert len(rows) > 0

    conn.close()
    try:
        import os
        os.remove(db_path)
    except Exception:
        pass
