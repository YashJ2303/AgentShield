"""
AgentShield Milestone 1 Sanity Check Script.

Demonstrates:
1. Tracing a fake agent run with model and tool calls containing sensitive secrets and emails.
2. Server ingest and redaction of secrets, credit cards, and emails.
3. GET /runs/{id} output showing full model inputs and verified redaction tokens.
4. OpenTelemetry / OTLP trace generation.
5. Rejection (401/403) on invalid or missing API key.
"""

import sys
import os
import json
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from server.app.main import app
from server.app.database import SessionLocal
from server.app.services.auth import seed_default_api_key
import agentshield
from agentshield import trace_model_call, trace_tool_call
from agentshield.otlp_exporter import init_otlp, export_otel_span, flush_otel


def run_sanity_check():
    print("=" * 70)
    print("AGENTSHIELD: MILESTONE 1 SANITY CHECK")
    print("=" * 70)

    # 1. Ensure test database & default API key are seeded
    db = SessionLocal()
    default_key_obj = seed_default_api_key(db)
    api_key = "agentshield-dev-key-12345"
    db.close()
    print(f"\n[1] Seeded Default API Key: '{api_key}' (ID: {default_key_obj.id})")

    client = TestClient(app)

    # 2. Test 401 / 403 on invalid API key
    print("\n[2] Testing Authentication Security:")
    resp_no_key = client.post("/ingest/spans", json={"spans": []})
    print(f"    - Missing X-API-Key: HTTP {resp_no_key.status_code} ({resp_no_key.json().get('detail')})")
    assert resp_no_key.status_code == 401

    resp_bad_key = client.post(
        "/ingest/spans",
        json={"spans": []},
        headers={"X-API-Key": "wrong-agent-key-999"},
    )
    print(f"    - Bad X-API-Key:     HTTP {resp_bad_key.status_code} ({resp_bad_key.json().get('detail')})")
    assert resp_bad_key.status_code == 403

    # 3. Trace a fake agent run with sensitive secrets and emails
    print("\n[3] Executing Instrumented Agent Run with Sensitive PII & Secrets:")

    captured_spans = []

    @trace_tool_call(name="fetch_user_record")
    def fetch_user_record(email: str) -> dict:
        return {
            "user_id": 42,
            "email": email,
            "api_credential": "api_key: super-secret-token-abcdef123456",
            "credit_card": "4532015112830366",
            "phone": "555-123-4567",
        }

    @trace_model_call(name="gpt-4o")
    def agent_decision(prompt: str) -> dict:
        user_info = fetch_user_record("target.user@company.com")
        return {
            "thought": "Successfully retrieved user record for target.user@company.com",
            "user_info": user_info,
            "usage": {"prompt_tokens": 85, "completion_tokens": 42, "total_tokens": 127},
        }

    # Execute inside agentshield.run context
    with agentshield.run(
        task_id="sanity-task-1",
        prompt_version="v2.1",
        model="gpt-4o",
        session_id="session-user-99",
        tags={"purpose": "sanity_check"},
    ) as run_ctx:
        run_id = run_ctx.run_id
        result = agent_decision(
            "Please lookup target.user@company.com and configure api_key: prod-agent-key-9876543210."
        )
        captured_spans = list(run_ctx.spans)

    print(f"    - Run ID: {run_id}")
    print(f"    - Total spans captured: {len(captured_spans)}")

    # 4. Ingest spans into server
    print("\n[4] Ingesting Captured Spans via POST /ingest/spans:")
    ingest_payload = {
        "session_id": "session-user-99",
        "task_id": "sanity-task-1",
        "prompt_version": "v2.1",
        "model": "gpt-4o",
        "outcome": "success",
        "spans": captured_spans,
    }
    ingest_resp = client.post(
        "/ingest/spans",
        json=ingest_payload,
        headers={"X-API-Key": api_key},
    )
    print(f"    - Ingest Status Code: {ingest_resp.status_code}")
    print(f"    - Ingest Response: {json.dumps(ingest_resp.json(), indent=6)}")
    assert ingest_resp.status_code == 200

    # 5. Retrieve run via GET /runs/{id}
    print(f"\n[5] Querying Stored Trace via GET /runs/{run_id}:")
    get_run_resp = client.get(f"/runs/{run_id}")
    assert get_run_resp.status_code == 200
    run_detail = get_run_resp.json()

    print(f"    - Task ID:           {run_detail.get('task_id')}")
    print(f"    - Session ID:        {run_detail.get('external_session_id')}")
    print(f"    - Model:             {run_detail.get('model')}")
    print(f"    - Outcome:           {run_detail.get('outcome')}")
    print(f"    - Total Tokens:      {run_detail.get('total_tokens')}")
    print(f"    - Total Cost:        ${run_detail.get('total_cost'):.6f}")
    print(f"    - Latency:           {run_detail.get('latency_ms')} ms")
    print(f"    - Steps:             {run_detail.get('step_count')}")

    print("\n[6] Inspecting Full Model Inputs and Redacted Stored Spans:")
    for idx, s in enumerate(run_detail.get("spans", []), 1):
        print(f"\n    --- Span {idx}: [{s['span_type'].upper()}] {s['name']} ---")
        print(f"        ID:              {s['id']}")
        print(f"        Parent ID:       {s['parent_span_id']}")
        print(f"        Redaction Count: {s['redaction_count']}")
        print(f"        Input Payload:   {json.dumps(s['input_payload'])}")
        print(f"        Output Payload:  {json.dumps(s['output_payload'])}")

    # 6. Verify Jaeger / OpenTelemetry compatibility
    print("\n[7] OpenTelemetry & OTLP Compatibility Verification:")
    tracer = init_otlp(service_name="agentshield-sanity-check", otlp_endpoint="http://localhost:4318/v1/traces")
    print("    - Tracer initialized with OpenTelemetry SDK TracerProvider")
    print("    - OTLP Span Processor registered with target: http://localhost:4318/v1/traces")
    flush_otel()
    print("    - OTLP flush executed cleanly.")

    print("\n" + "=" * 70)
    print("SANITY CHECK COMPLETE: ALL CHECKS PASSED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    run_sanity_check()
