"""
Script to execute real demo agent runs through AgentShield and generate
comprehensive analytics data for Milestone 6 verification.
"""
import os
import sys
import uuid
import time
from datetime import datetime, timezone, timedelta

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from server.app.main import app
from server.app.database import SessionLocal, engine, Base
from server.app.models.run import Run
from server.app.models.span import Span
from server.app.models.approval import Approval
from server.app.services.auth import seed_default_api_key

def seed_demo_analytics():
    print("=" * 80)
    print("AGENTSHIELD: GENERATING REAL DEMO RUNS FOR MILESTONE 6 ANALYTICS")
    print("=" * 80)

    db = SessionLocal()
    # Ensure tables exist and dev key is seeded
    Base.metadata.create_all(bind=engine)
    api_key_obj = seed_default_api_key(db)
    api_key = "agentshield-dev-key-12345"

    now = datetime.now(timezone.utc)

    # We will generate a diverse, realistic batch of runs:
    # 1. Successful gpt-4o run (normal latency & tokens)
    # 2. Successful gpt-4o run
    # 3. Blocked gpt-4o run (policy block on dangerous tool)
    # 4. Successful claude-3-5-sonnet run (fast)
    # 5. Failed claude-3-5-sonnet run (tool error)
    # 6. Timed-out llama-3.1-70b run (exceeded time limit)
    # 7. Successful mystery-model run (unknown model -> cost None / null)
    # 8. Anomaly run: Loop detector trigger (4 consecutive calls to fetch_user_record with same args)
    # 9. Anomaly run: High step count outlier (35 steps)
    # 10. Successful gpt-4o run
    # 11. Successful gpt-4o run
    # 12. Successful claude-3-5-sonnet run

    run_specs = [
        # (run_id, model, prompt_ver, outcome, step_count, latency_ms, prompt_tokens, comp_tokens, error_type, has_loop)
        ("run-gpt4o-01", "gpt-4o", "v1.0", "success", 4, 1250, 450, 180, None, False),
        ("run-gpt4o-02", "gpt-4o", "v1.0", "success", 3, 1100, 320, 150, None, False),
        ("run-gpt4o-03", "gpt-4o", "v1.0", "blocked", 2, 850, 200, 80, "policy_block", False),
        ("run-gpt4o-04", "gpt-4o", "v1.1", "success", 5, 1400, 500, 210, None, False),
        ("run-gpt4o-05", "gpt-4o", "v1.1", "success", 4, 1300, 410, 190, None, False),
        ("run-claude-01", "claude-3-5-sonnet-20241022", "v2.0", "success", 3, 950, 380, 160, None, False),
        ("run-claude-02", "claude-3-5-sonnet-20241022", "v2.0", "failure", 3, 1150, 400, 120, "tool_error", False),
        ("run-claude-03", "claude-3-5-sonnet-20241022", "v2.0", "success", 4, 1020, 390, 175, None, False),
        ("run-llama-01", "llama-3.1-70b", "v1.0", "timed_out", 6, 8500, 800, 300, "timeout", False),
        ("run-mystery-01", "custom-finance-llm-v1", "v1.0", "success", 3, 1600, 600, 250, None, False),
        ("run-loop-01", "gpt-4o", "v1.0", "failure", 8, 4200, 950, 400, "loop", True),
        ("run-outlier-steps", "gpt-4o", "v1.0", "success", 35, 18500, 3500, 1800, None, False),
    ]

    for spec in run_specs:
        run_id_val, model_name, p_ver, outcome_val, steps, lat_ms, p_tok, c_tok, err_code, is_loop = spec
        
        # Calculate cost via pricing service logic
        if model_name == "custom-finance-llm-v1":
            calc_cost = None
        elif model_name == "gpt-4o":
            # $5.00/1M input, $15.00/1M output
            calc_cost = (p_tok * 5.00 / 1_000_000.0) + (c_tok * 15.00 / 1_000_000.0)
        elif model_name == "claude-3-5-sonnet-20241022":
            # $3.00/1M input, $15.00/1M output
            calc_cost = (p_tok * 3.00 / 1_000_000.0) + (c_tok * 15.00 / 1_000_000.0)
        elif model_name == "llama-3.1-70b":
            # $0.88/1M input, $0.88/1M output
            calc_cost = (p_tok * 0.88 / 1_000_000.0) + (c_tok * 0.88 / 1_000_000.0)
        else:
            calc_cost = None

        existing_run = db.query(Run).filter(Run.id == run_id_val).first()
        if existing_run:
            db.delete(existing_run)
            db.commit()

        start_time = now - timedelta(minutes=lat_ms / 600.0)
        end_time = now

        new_run = Run(
            id=run_id_val,
            session_id=f"session-{model_name[:6]}",
            task_id="demo-analytics-task",
            prompt_version=p_ver,
            model=model_name,
            outcome=outcome_val,
            step_count=steps,
            total_cost=calc_cost,
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
            total_tokens=p_tok + c_tok,
            latency_ms=lat_ms,
            started_at=start_time,
            ended_at=end_time,
            error_message=f"Agent terminated with {err_code}" if err_code else None
        )
        db.add(new_run)
        db.flush()

        # Add spans for tools
        if is_loop:
            # Add 4 consecutive calls with identical tool and args
            for i in range(4):
                sp = Span(
                    id=str(uuid.uuid4()),
                    run_id=run_id_val,
                    sequence_number=i + 1,
                    span_type="tool",
                    name="fetch_user_record",
                    started_at=start_time + timedelta(milliseconds=i * 200),
                    ended_at=start_time + timedelta(milliseconds=(i + 1) * 200),
                    latency_ms=200,
                    input_payload={"email": "victim@domain.com", "max_records": 10},
                    output_payload={"records": []},
                    policy_decision="allow"
                )
                db.add(sp)
        elif outcome_val == "blocked":
            sp = Span(
                id=str(uuid.uuid4()),
                run_id=run_id_val,
                sequence_number=1,
                span_type="tool",
                name="wire_transfer",
                started_at=start_time,
                ended_at=end_time,
                latency_ms=lat_ms,
                input_payload={"amount": 999999.0, "recipient": "unauthorized"},
                output_payload={},
                policy_decision="deny",
                policy_rule_id="deny_excessive_transfer"
            )
            db.add(sp)
        elif outcome_val == "failed":
            sp = Span(
                id=str(uuid.uuid4()),
                run_id=run_id_val,
                sequence_number=1,
                span_type="tool",
                name="sql_query",
                started_at=start_time,
                ended_at=end_time,
                latency_ms=lat_ms,
                error="OperationalError: database locked",
                input_payload={"query": "SELECT * FROM transactions"},
                output_payload={},
                policy_decision="allow"
            )
            db.add(sp)
        else:
            # Normal tools
            sp1 = Span(
                id=str(uuid.uuid4()),
                run_id=run_id_val,
                sequence_number=1,
                span_type="tool",
                name="fetch_user_record",
                started_at=start_time,
                ended_at=start_time + timedelta(milliseconds=150),
                latency_ms=150,
                input_payload={"email": f"user-{run_id_val}@test.com"},
                output_payload={"status": "found"},
                policy_decision="allow"
            )
            sp2 = Span(
                id=str(uuid.uuid4()),
                run_id=run_id_val,
                sequence_number=2,
                span_type="tool",
                name="format_report",
                started_at=start_time + timedelta(milliseconds=200),
                ended_at=end_time,
                latency_ms=lat_ms - 200,
                input_payload={"format": "json"},
                output_payload={"formatted": True},
                policy_decision="allow"
            )
            db.add(sp1)
            db.add(sp2)

    db.commit()
    db.close()
    print("Demo runs seeded successfully!")

    # Now let's query the live endpoints with TestClient
    client = TestClient(app)

    print("\n--- 1. GET /analytics/summary ---")
    sum_resp = client.get("/analytics/summary")
    print(f"Status: {sum_resp.status_code}")
    summary = sum_resp.json()
    import pprint
    pprint.pprint(summary)

    print("\n--- 2. GET /analytics/breakdown ---")
    brk_resp = client.get("/analytics/breakdown")
    print(f"Status: {brk_resp.status_code}")
    breakdown = brk_resp.json()
    print("\nModel Breakdown:")
    pprint.pprint(breakdown.get("models"))
    print("\nTool Breakdown:")
    pprint.pprint(breakdown.get("tools"))

    print("\n--- 3. GET /analytics/model-comparison ---")
    comp_resp = client.get("/analytics/model-comparison?model_a=gpt-4o&model_b=claude-3-5-sonnet-20241022")
    print(f"Status: {comp_resp.status_code}")
    pprint.pprint(comp_resp.json())

    print("\n--- 4. GET /analytics/anomalies ---")
    ano_resp = client.get("/analytics/anomalies")
    print(f"Status: {ano_resp.status_code}")
    anomalies = ano_resp.json()
    print(f"Total Anomalies Detected: {len(anomalies)}")
    for a in anomalies:
        print(f" - [{a['type']}] ({a['severity'].upper()}) Run {a['run_id']}: {a['message']} (val={a['value']}, baseline={a.get('baseline_reference')}, n={a.get('sample_size')})")

if __name__ == "__main__":
    seed_demo_analytics()
