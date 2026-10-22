"""
Tests for Milestone 9 (Reduced): Batch Incident Replay & Reporting.

Covers:
1. Batch replay over a list of run_ids (POST /replay/batch).
2. Hand-computed batch aggregation values (mean fidelity, mean truncated fidelity, cache-miss rate, regression rate).
3. Markdown and JSON aggregate report format verification.
4. Error handling when a run_id is missing/not found in database.
5. Replays stay tagged and strictly excluded from analytics queries.
"""
import uuid
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from server.app.main import app
from server.app.database import SessionLocal
from server.app.models.run import Run
from server.app.models.span import Span
from server.app.models.replay import Replay
from server.app.services.auth import seed_default_api_key
from server.app.services.analytics_service import get_analytics_summary
from server.app.config import settings

client = TestClient(app)
DEV_KEY = "agentshield-dev-key-12345"


@pytest.fixture(autouse=True)
def ensure_api_key():
    db = SessionLocal()
    seed_default_api_key(db)
    db.close()


def test_batch_replay_endpoint_and_hand_computed_aggregation():
    """
    Verify POST /replay/batch across 2 runs with hand-computed aggregate figures:
    Run 1: Clean exact reproduction (Fidelity = 1.0, Truncated = 1.0, Miss Rate = 0.0, Reg = False)
    Run 2: Policy denial on bash_exec:
           Canonical Rule: Denied calls are excluded from the allowed executed sequence.
           Allowed executed calls = [] (0 calls vs 1 recorded, Levenshtein dist 1) -> S_tool = 0.0
           Matched steps k = 0 (tool blocked before execution, no recorded outputs consumed) -> S_args = 0.0
           S_outcome = 0.0 (blocked/failure vs success)
           Composite Fidelity = 0.4*0.0 + 0.3*0.0 + 0.3*0.0 = 0.0000
           Truncated Fidelity = 0.0000, Miss Rate = 0.0, Reg = True

    Hand-computed aggregates:
      Mean Fidelity = (1.0 + 0.00) / 2 = 0.5000
      Mean Truncated Fidelity = (1.0 + 0.00) / 2 = 0.5000
      Mean Cache Miss Rate = (0.0 + 0.0) / 2 = 0.0000
      Regressions Count = 1
      Regression Rate = 1 / 2 = 0.5000 (50.0%)
    """
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    run_id_1 = f"batch-run-1-{uuid.uuid4().hex[:8]}"
    run_id_2 = f"batch-run-2-{uuid.uuid4().hex[:8]}"

    # Run 1: clean run
    r1 = Run(id=run_id_1, model="gpt-4o", outcome="success", started_at=now)
    s1 = Span(
        id=str(uuid.uuid4()),
        run_id=run_id_1,
        sequence_number=1,
        span_type="tool",
        name="calculator",
        input_payload={"expr": "2 + 2"},
        output_payload={"result": 4},
        started_at=now,
        policy_decision="allow",
    )

    # Run 2: bash execution run
    r2 = Run(id=run_id_2, model="gpt-4o", outcome="success", started_at=now)
    s2 = Span(
        id=str(uuid.uuid4()),
        run_id=run_id_2,
        sequence_number=1,
        span_type="tool",
        name="bash_exec",
        input_payload={"cmd": "uname -a"},
        output_payload={"stdout": "Linux"},
        started_at=now,
        policy_decision="allow",
    )

    db.add(r1)
    db.add(s1)
    db.add(r2)
    db.add(s2)
    db.commit()
    db.close()

    candidate_policy = """
version: "1"
default_action: allow
rules:
  - id: deny_shell
    tool: bash_exec
    action: deny
"""

    try:
        resp = client.post(
            "/replay/batch",
            headers={"X-API-Key": DEV_KEY, "X-Admin-Token": settings.ADMIN_TOKEN},
            json={
                "run_ids": [run_id_1, run_id_2],
                "target_model": "gpt-4o",
                "candidate_policy_yaml": candidate_policy,
                "num_samples": 1,
                "matching_threshold": 0.85,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        # Check total counts
        assert data["total_requested"] == 2
        assert data["successful_replays"] == 2
        assert data["failed_replays"] == 0

        # Check hand-computed mathematical aggregates
        assert data["mean_fidelity"] == 0.5000
        assert data["mean_truncated_fidelity"] == 0.5000
        assert data["mean_cache_miss_rate"] == 0.0000
        assert data["regressions_detected"] == 1
        assert data["regression_rate"] == 0.5000

        # Check item summaries
        items = data["items"]
        assert len(items) == 2
        item1 = next(it for it in items if it["run_id"] == run_id_1)
        assert item1["status"] == "replayed"
        assert item1["fidelity_score"] == 1.0
        assert item1["regression_detected"] is False

        item2 = next(it for it in items if it["run_id"] == run_id_2)
        assert item2["status"] == "replayed"
        assert item2["fidelity_score"] == 0.0000
        assert item2["regression_detected"] is True

    finally:
        clean_db = SessionLocal()
        clean_db.query(Span).filter(Span.run_id.in_([run_id_1, run_id_2])).delete()
        clean_db.query(Replay).filter(Replay.original_run_id.in_([run_id_1, run_id_2])).delete()
        clean_db.query(Run).filter(Run.id.in_([run_id_1, run_id_2])).delete()
        clean_db.commit()
        clean_db.close()


def test_batch_replay_report_format_markdown_and_json():
    """
    Verify that batch replay generates both human-readable Markdown and structured JSON reports.
    """
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    run_id = f"batch-report-run-{uuid.uuid4().hex[:8]}"

    r = Run(id=run_id, model="claude-3-5-sonnet", outcome="success", started_at=now)
    s = Span(
        id=str(uuid.uuid4()),
        run_id=run_id,
        sequence_number=1,
        span_type="tool",
        name="web_search",
        input_payload={"q": "AgentShield"},
        output_payload={"snippet": "Security Layer"},
        started_at=now,
        policy_decision="allow",
    )
    db.add(r)
    db.add(s)
    db.commit()
    db.close()

    try:
        resp = client.post(
            "/replay/batch",
            headers={"X-API-Key": DEV_KEY, "X-Admin-Token": settings.ADMIN_TOKEN},
            json={
                "run_ids": [run_id],
                "num_samples": 1,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        # 1. Verify Markdown report content and structure
        md = data["markdown_report"]
        assert "# AgentShield Batch Incident Replay Report" in md
        assert "**Total Runs Requested**: 1" in md
        assert "**Successfully Replayed**: 1" in md
        assert "## Replayed Runs Detail Table" in md
        assert "| Run ID | Status | Model | Overall Fidelity |" in md
        assert f"`{run_id[:16]}...`" in md

        # 2. Verify JSON report content and schema
        jr = data["json_report"]
        assert "summary" in jr
        assert jr["summary"]["total_requested"] == 1
        assert jr["summary"]["successful_replays"] == 1
        assert jr["summary"]["mean_fidelity"] == 1.0
        assert "runs" in jr
        assert len(jr["runs"]) == 1
        assert jr["runs"][0]["run_id"] == run_id
        assert jr["runs"][0]["status"] == "replayed"
        assert "generated_at" in jr

    finally:
        clean_db = SessionLocal()
        clean_db.query(Span).filter(Span.run_id == run_id).delete()
        clean_db.query(Replay).filter(Replay.original_run_id == run_id).delete()
        clean_db.query(Run).filter(Run.id == run_id).delete()
        clean_db.commit()
        clean_db.close()


def test_batch_replay_missing_run_error_handling():
    """
    Verify that when one or more run_ids in the batch do not exist in the database,
    the batch replay handles the missing runs gracefully without throwing 404 or 500,
    records them with status 'not_found', and computes aggregate metrics over existing runs.
    """
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    valid_run_id = f"batch-valid-{uuid.uuid4().hex[:8]}"
    missing_run_id = f"non-existent-uuid-{uuid.uuid4().hex[:8]}"

    r = Run(id=valid_run_id, model="gpt-4o", outcome="success", started_at=now)
    s = Span(
        id=str(uuid.uuid4()),
        run_id=valid_run_id,
        sequence_number=1,
        span_type="tool",
        name="calculator",
        input_payload={"a": 5, "b": 5},
        output_payload={"ans": 10},
        started_at=now,
        policy_decision="allow",
    )
    db.add(r)
    db.add(s)
    db.commit()
    db.close()

    try:
        resp = client.post(
            "/replay/batch",
            headers={"X-API-Key": DEV_KEY, "X-Admin-Token": settings.ADMIN_TOKEN},
            json={
                "run_ids": [valid_run_id, missing_run_id],
                "num_samples": 1,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_requested"] == 2
        assert data["successful_replays"] == 1
        assert data["failed_replays"] == 1
        assert missing_run_id in data["missing_run_ids"]

        items = data["items"]
        missing_item = next(it for it in items if it["run_id"] == missing_run_id)
        assert missing_item["status"] == "not_found"
        assert f"Run '{missing_run_id}' not found" in missing_item["error"]

        valid_item = next(it for it in items if it["run_id"] == valid_run_id)
        assert valid_item["status"] == "replayed"
        assert valid_item["fidelity_score"] == 1.0

        # Mean fidelity is computed over valid replayed runs (1.0)
        assert data["mean_fidelity"] == 1.0

    finally:
        clean_db = SessionLocal()
        clean_db.query(Span).filter(Span.run_id == valid_run_id).delete()
        clean_db.query(Replay).filter(Replay.original_run_id == valid_run_id).delete()
        clean_db.query(Run).filter(Run.id == valid_run_id).delete()
        clean_db.commit()
        clean_db.close()


def test_batch_replays_isolated_from_analytics():
    """
    Verify that replay executions generated during batch replay do not leak
    into production analytics summaries when include_replays=False.
    """
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    run_id = f"batch-iso-{uuid.uuid4().hex[:8]}"

    # Seed baseline run
    r = Run(id=run_id, model="gpt-4o", outcome="success", total_cost=0.25, started_at=now, tags={})
    s = Span(
        id=str(uuid.uuid4()),
        run_id=run_id,
        sequence_number=1,
        span_type="tool",
        name="test_tool",
        input_payload={"arg": 1},
        output_payload={"out": 1},
        started_at=now,
        policy_decision="allow",
    )
    db.add(r)
    db.add(s)
    db.commit()
    db.close()

    try:
        # Pre-replay baseline analytics count
        db_check = SessionLocal()
        summary_before = get_analytics_summary(db=db_check, include_replays=False)
        db_check.close()

        # Run batch replay
        resp = client.post(
            "/replay/batch",
            headers={"X-API-Key": DEV_KEY, "X-Admin-Token": settings.ADMIN_TOKEN},
            json={
                "run_ids": [run_id],
                "num_samples": 1,
            },
        )
        assert resp.status_code == 200

        # Post-replay analytics count with include_replays=False must be unaffected
        db_check2 = SessionLocal()
        summary_after = get_analytics_summary(db=db_check2, include_replays=False)
        db_check2.close()

        assert summary_after.total_runs == summary_before.total_runs

    finally:
        clean_db = SessionLocal()
        clean_db.query(Span).filter(Span.run_id == run_id).delete()
        clean_db.query(Replay).filter(Replay.original_run_id == run_id).delete()
        clean_db.query(Run).filter(Run.id == run_id).delete()
        clean_db.commit()
        clean_db.close()
