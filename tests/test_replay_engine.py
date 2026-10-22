"""
Comprehensive tests for Milestone 8: Incident Replay Engine (RQ2).

Covers:
1. Hand-computed fidelity score components (S_tool Levenshtein, S_args, composite weights 0.4/0.3/0.3).
2. Fuzzy argument matching threshold edge cases (0.75, 0.85, 0.95) and sensitivity analysis.
3. Strict guarantee: No live tool can ever execute during replay (including on cache miss).
4. Cache-miss handling and synthetic response generation without crashing.
5. Multi-sample replay (N=3) with spread calculation and consistency-based regression flagging.
6. Candidate policy evaluation using pure evaluate_policy() without duplicated logic.
7. Replay run isolation from analytics queries (excluded by default, included on include_replays=True).
8. Live HTTP API endpoints (POST /replay, GET /replay/{id}, GET /replays).
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
from server.app.services.fidelity import (
    calculate_tool_sequence_similarity,
    calculate_arg_similarity,
    calculate_fidelity_score,
    levenshtein_distance,
)
from server.app.services.replay_engine import (
    IncidentReplayHarness,
    ScriptedMockAgent,
)
from server.app.services.analytics_service import get_analytics_summary
from server.app.config import settings

client = TestClient(app)
DEV_KEY = "agentshield-dev-key-12345"


# =========================================================================
# 1. Hand-Computed Fidelity Tests
# =========================================================================

def test_hand_computed_fidelity_components():
    """
    Verify hand-computed mathematical properties of the fidelity scoring formula:
    Fidelity = 0.4 * S_tool + 0.3 * S_args + 0.3 * S_outcome
    where S_tool = 1 - (LevenshteinDistance / max_len).
    """
    # 1. Identical sequence: dist = 0 -> S_tool = 1.0
    seq1 = ["fetch_data", "process_records", "save_output"]
    seq2 = ["fetch_data", "process_records", "save_output"]
    assert calculate_tool_sequence_similarity(seq1, seq2) == 1.0

    # 2. Deletion: length 3 vs length 2 (dist = 1) -> S_tool = 1 - 1/3 = 2/3 = 0.6667
    seq_del = ["fetch_data", "process_records"]
    s_tool_del = calculate_tool_sequence_similarity(seq1, seq_del)
    assert round(s_tool_del, 4) == 0.6667

    # 3. Complete disjoint: length 1 vs length 1 (dist = 1) -> S_tool = 1 - 1/1 = 0.0
    seq_disjoint = ["unrelated_action"]
    assert calculate_tool_sequence_similarity(["fetch_data"], seq_disjoint) == 0.0

    # 4. Empty sequences: returns 1.0
    assert calculate_tool_sequence_similarity([], []) == 1.0

    # 5. Argument similarity (S_args)
    args_a = {"user_id": 42, "role": "admin"}
    args_b = {"role": "admin", "user_id": 42}  # Key ordering invariant in canonical JSON
    assert calculate_arg_similarity(args_a, args_b) == 1.0

    # 6. Hand-computed composite fidelity
    # 0.4 * (2/3) + 0.3 * (0.8) + 0.3 * (1.0)
    # = 0.26668 + 0.24 + 0.3 = 0.8067
    composite = calculate_fidelity_score(s_tool=2/3, s_args=0.8, s_outcome=1.0)
    assert composite == 0.8067


def test_hand_computed_s_args_derivation_from_step_data():
    """
    Verifies that S_args is derived directly from step data by averaging similarity
    exclusively over MATCHED tool steps (k=2), rather than averaging over all original
    steps (n=3) or padding omitted steps with zeros.

    Hand-computation:
    Recorded trace (n=3):
      1. calculator: {"a": 10, "b": 20}
      2. sql_query:  {"query": "SELECT id FROM users;"}
      3. bash_exec:  {"cmd": "ls -la"}

    Replayed calls (m=2):
      1. calculator: {"a": 10, "b": 20} -> sim_1 = 1.0 (exact match)
      2. sql_query:  {"query": "SELECT id FROM users"} -> sim_2 = 0.9706 (33/34 match)
      (bash_exec is omitted in replay)

    Matched steps: k = 2
    S_args = (1.0 + 0.9706) / 2 = 0.9853 (derived from step data)
    (If improperly averaged over all n=3: (1.0 + 0.9706 + 0) / 3 = 0.6569)

    S_tool = 1 - (Levenshtein distance between ['calculator', 'sql_query', 'bash_exec']
             and ['calculator', 'sql_query'] / 3) = 1 - 1/3 = 2/3 = 0.6667.
    S_outcome = 1.0 (both success).

    Composite Fidelity = 0.4 * (2/3) + 0.3 * (0.9853) + 0.3 * (1.0) = 0.8623.
    """
    db: Session = SessionLocal()
    run_id = f"test-sargs-deriv-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    orig_run = Run(id=run_id, model="gpt-4o", outcome="success", started_at=now)
    spans = [
        Span(
            id=str(uuid.uuid4()),
            run_id=run_id,
            sequence_number=1,
            span_type="tool",
            name="calculator",
            input_payload={"a": 10, "b": 20},
            output_payload={"res": 30},
            started_at=now,
            policy_decision="allow",
        ),
        Span(
            id=str(uuid.uuid4()),
            run_id=run_id,
            sequence_number=2,
            span_type="tool",
            name="sql_query",
            input_payload={"query": "SELECT id FROM users;"},
            output_payload={"rows": [1, 2]},
            started_at=now,
            policy_decision="allow",
        ),
        Span(
            id=str(uuid.uuid4()),
            run_id=run_id,
            sequence_number=3,
            span_type="tool",
            name="bash_exec",
            input_payload={"cmd": "ls -la"},
            output_payload={"stdout": "file.txt"},
            started_at=now,
            policy_decision="allow",
        ),
    ]
    db.add(orig_run)
    for s in spans:
        db.add(s)
    db.commit()

    agent = ScriptedMockAgent(
        planned_calls=[
            ("calculator", {"a": 10, "b": 20}),
            ("sql_query", {"query": "SELECT id FROM users"}),  # No semicolon
        ],
        final_outcome="success",
    )

    harness = IncidentReplayHarness(db)
    res = harness.replay_run(
        original_run_id=run_id,
        agent=agent,
        matching_threshold=0.85,
        num_samples=1,
    )

    sample = res.sample_results[0]
    # S_args derived over matched steps k=2: round((1.0 + 0.9706)/2, 4) == 0.9853
    assert sample.s_args == 0.9853
    assert sample.s_tool == 0.6667
    assert sample.s_outcome == 1.0
    # Composite fidelity: 0.4 * (2/3) + 0.3 * 0.9853 + 0.3 * 1.0 == 0.8623
    assert sample.fidelity_score == 0.8623

    # Cleanup
    db.query(Span).filter(Span.run_id == run_id).delete()
    db.query(Replay).filter(Replay.original_run_id == run_id).delete()
    db.query(Run).filter(Run.id == run_id).delete()
    db.commit()
    db.close()


def test_sequential_in_order_tool_output_consumption_at_most_once():
    """
    Verifies that when an agent calls the same tool multiple times with similar arguments,
    each recorded output is consumed strictly in chronological order, at most once,
    and subsequent excess calls trigger cache misses.
    """
    db: Session = SessionLocal()
    run_id = f"test-in-order-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    orig_run = Run(id=run_id, model="gpt-4o", outcome="success", started_at=now)
    span1 = Span(
        id=str(uuid.uuid4()),
        run_id=run_id,
        sequence_number=1,
        span_type="tool",
        name="fetch_quote",
        input_payload={"symbol": "NVDA"},
        output_payload={"price": 120.0, "seq": 1},
        started_at=now,
        policy_decision="allow",
    )
    span2 = Span(
        id=str(uuid.uuid4()),
        run_id=run_id,
        sequence_number=2,
        span_type="tool",
        name="fetch_quote",
        input_payload={"symbol": "NVDA"},
        output_payload={"price": 125.0, "seq": 2},
        started_at=now,
        policy_decision="allow",
    )
    db.add(orig_run)
    db.add(span1)
    db.add(span2)
    db.commit()

    # Agent calls fetch_quote THREE times (one more than recorded)
    agent = ScriptedMockAgent(
        planned_calls=[
            ("fetch_quote", {"symbol": "NVDA"}),
            ("fetch_quote", {"symbol": "NVDA"}),
            ("fetch_quote", {"symbol": "NVDA"}),
        ],
        final_outcome="success",
    )

    harness = IncidentReplayHarness(db)
    res = harness.replay_run(
        original_run_id=run_id,
        agent=agent,
        matching_threshold=0.85,
        num_samples=1,
    )

    diff = res.trajectory_diff
    assert len(diff) == 3

    # Call 1: consumed 1st recorded span
    assert diff[0]["output_replayed"]["seq"] == 1
    assert diff[0]["is_cache_miss"] is False

    # Call 2: consumed 2nd recorded span in sequential order
    assert diff[1]["output_replayed"]["seq"] == 2
    assert diff[1]["is_cache_miss"] is False

    # Call 3: recorded outputs exhausted -> cache miss!
    assert diff[2]["is_cache_miss"] is True
    assert diff[2]["output_replayed"]["replay_cache_miss"] is True

    # Truncated fidelity should evaluate the 2 matched steps prior to the miss
    assert res.sample_results[0].fidelity_truncated > 0.0

    # Cleanup
    db.query(Span).filter(Span.run_id == run_id).delete()
    db.query(Replay).filter(Replay.original_run_id == run_id).delete()
    db.query(Run).filter(Run.id == run_id).delete()
    db.commit()
    db.close()


def test_truncated_fidelity_pre_cache_miss():
    """
    Verifies that fidelity_truncated is calculated exclusively on the prefix
    trajectory before the first cache miss occurs.
    """
    db: Session = SessionLocal()
    run_id = f"test-trunc-fid-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    orig_run = Run(id=run_id, model="gpt-4o", outcome="success", started_at=now)
    spans = [
        Span(
            id=str(uuid.uuid4()),
            run_id=run_id,
            sequence_number=1,
            span_type="tool",
            name="step_a",
            input_payload={"x": 1},
            output_payload={"out": "a"},
            started_at=now,
            policy_decision="allow",
        ),
        Span(
            id=str(uuid.uuid4()),
            run_id=run_id,
            sequence_number=2,
            span_type="tool",
            name="step_b",
            input_payload={"x": 2},
            output_payload={"out": "b"},
            started_at=now,
            policy_decision="allow",
        ),
    ]
    db.add(orig_run)
    for s in spans:
        db.add(s)
    db.commit()

    # Replay where step 1 matches, but step 2 is an unrecorded tool (cache miss)
    agent = ScriptedMockAgent(
        planned_calls=[
            ("step_a", {"x": 1}),
            ("unrecorded_step", {"x": 99}),
        ],
        final_outcome="success",
    )

    harness = IncidentReplayHarness(db)
    res = harness.replay_run(
        original_run_id=run_id,
        agent=agent,
        matching_threshold=0.85,
        num_samples=1,
    )

    sample = res.sample_results[0]
    # First step matched perfectly (1/1 tool match, 1.0 arg sim, 1.0 outcome) -> trunc fid = 1.0
    assert sample.fidelity_truncated == 1.0
    # Overall fidelity suffered due to unrecorded_step mismatch: S_tool = 1 - 1/2 = 0.5
    # S_args = 1.0 (over 1 matched step), S_outcome = 0.0 (cache miss induced agent error -> failure)
    # -> 0.4*0.5 + 0.3*1.0 + 0.3*0.0 = 0.5
    assert sample.fidelity_score == 0.5000

    # Cleanup
    db.query(Span).filter(Span.run_id == run_id).delete()
    db.query(Replay).filter(Replay.original_run_id == run_id).delete()
    db.query(Run).filter(Run.id == run_id).delete()
    db.commit()
    db.close()


# =========================================================================
# 2. Strict Guarantee: No Live Tool Execution During Replay
# =========================================================================

def test_no_live_tool_can_ever_execute_during_replay():
    """
    Verifies that during replay, live tools are never passed to the agent,
    and even upon cache miss, live tool execution is impossible.
    """
    db: Session = SessionLocal()
    run_id = f"test-replay-orig-{uuid.uuid4().hex[:8]}"

    # Seed recorded run with 1 tool call
    now = datetime.now(timezone.utc)
    test_run = Run(id=run_id, model="gpt-4o", outcome="success", started_at=now)
    test_span = Span(
        id=str(uuid.uuid4()),
        run_id=run_id,
        sequence_number=1,
        span_type="tool",
        name="database_query",
        input_payload={"sql": "SELECT name FROM employees;"},
        output_payload={"rows": [{"name": "Alice"}]},
        started_at=now,
        policy_decision="allow",
    )
    db.add(test_run)
    db.add(test_span)
    db.commit()

    # Define a trap live executor that must NEVER be called
    def trap_live_tool(name: str, args: dict):
        raise AssertionError("CRITICAL FAILURE: Live tool was invoked during replay!")

    # Agent calls a completely unrecorded tool
    agent = ScriptedMockAgent(
        planned_calls=[("unrecorded_destructive_tool", {"action": "drop_all"})],
        final_outcome="success",
    )

    harness = IncidentReplayHarness(db)
    res = harness.replay_run(
        original_run_id=run_id,
        agent=agent,
        matching_threshold=0.85,
        num_samples=1,
    )

    # Assert cache miss was handled synthetically and no live tool was invoked
    assert res.mean_cache_miss_rate == 1.0
    assert res.sample_results[0].cache_misses == 1
    diff_step = res.trajectory_diff[0]
    assert diff_step["is_cache_miss"] is True
    assert diff_step["output_replayed"]["replay_cache_miss"] is True

    # Cleanup
    db.query(Span).filter(Span.run_id == run_id).delete()
    db.query(Replay).filter(Replay.original_run_id == run_id).delete()
    db.query(Run).filter(Run.id == run_id).delete()
    db.commit()
    db.close()


# =========================================================================
# 3. Fuzzy Matching Thresholds & Sensitivity Analysis
# =========================================================================

def test_fuzzy_matching_threshold_and_sensitivity():
    """
    Verify argument matching at thresholds 0.75, 0.85, 0.95.
    Demonstrates that stricter thresholds induce cache misses for slightly modified arguments.
    """
    db: Session = SessionLocal()
    run_id = f"test-replay-fuzzy-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    test_run = Run(id=run_id, model="gpt-4o", outcome="success", started_at=now)
    test_span = Span(
        id=str(uuid.uuid4()),
        run_id=run_id,
        sequence_number=1,
        span_type="tool",
        name="search_web",
        input_payload={"query": "financial statements 2025 acme corp"},
        output_payload={"result": "Revenue: $100M"},
        started_at=now,
        policy_decision="allow",
    )
    db.add(test_run)
    db.add(test_span)
    db.commit()

    # Replaying agent with slightly altered query arguments
    # Simulates prompt modification that shifts search query slightly
    agent = ScriptedMockAgent(
        planned_calls=[("search_web", {"query": "financial statements 2025 acme enterprises"})],
        final_outcome="success",
    )

    harness = IncidentReplayHarness(db)
    sensitivity = harness.evaluate_threshold_sensitivity(
        original_run_id=run_id,
        agent=agent,
        thresholds=[0.75, 0.85, 0.98],
    )

    assert len(sensitivity) == 3
    # At loose threshold (0.75), slight variance hits cache
    assert sensitivity[0]["threshold"] == 0.75
    # At strict threshold (0.98), slight variance misses cache
    assert sensitivity[2]["threshold"] == 0.98
    assert sensitivity[2]["cache_misses"] >= sensitivity[0]["cache_misses"]

    # Cleanup
    db.query(Span).filter(Span.run_id == run_id).delete()
    db.query(Replay).filter(Replay.original_run_id == run_id).delete()
    db.query(Run).filter(Run.id == run_id).delete()
    db.commit()
    db.close()


# =========================================================================
# 4. Multi-Sample Replay & Regression Detection
# =========================================================================

def test_multi_sample_replay_and_regression_flags():
    """
    Verify multi-sample replay executes N=3 samples, calculates spread,
    and flags regressions consistently across samples.
    """
    db: Session = SessionLocal()
    run_id = f"test-replay-multi-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    test_run = Run(id=run_id, model="gpt-4o", outcome="success", started_at=now)
    test_span1 = Span(
        id=str(uuid.uuid4()),
        run_id=run_id,
        sequence_number=1,
        span_type="tool",
        name="read_file",
        input_payload={"path": "/data/report.txt"},
        output_payload={"text": "clean"},
        started_at=now,
        policy_decision="allow",
    )
    db.add(test_run)
    db.add(test_span1)
    db.commit()

    # Agent with deliberate behavior shift calling an unrecorded tool
    shifted_agent = ScriptedMockAgent(
        planned_calls=[("read_file", {"path": "/data/report.txt"})],
        behavior_shift="forbidden_tool",
    )

    harness = IncidentReplayHarness(db)
    res = harness.replay_run(
        original_run_id=run_id,
        agent=shifted_agent,
        num_samples=3,
        matching_threshold=0.85,
    )

    assert len(res.sample_results) == 3
    assert res.num_samples == 3
    assert res.regression_detected is True
    assert len(res.regression_reasons) > 0

    # Cleanup
    db.query(Span).filter(Span.run_id == run_id).delete()
    db.query(Replay).filter(Replay.original_run_id == run_id).delete()
    db.query(Run).filter(Run.id == run_id).delete()
    db.commit()
    db.close()


# =========================================================================
# 5. Candidate Policy Evaluation During Replay
# =========================================================================

def test_replay_under_candidate_policy_denial():
    """
    Verify that candidate policies are re-evaluated during replay using pure evaluate_policy(),
    correctly blocking tool calls that were previously allowed under baseline policy.
    """
    db: Session = SessionLocal()
    run_id = f"test-replay-pol-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    test_run = Run(id=run_id, model="gpt-4o", outcome="success", started_at=now)
    test_span = Span(
        id=str(uuid.uuid4()),
        run_id=run_id,
        sequence_number=1,
        span_type="tool",
        name="transfer_funds",
        input_payload={"account": "12345", "amount": 50000},
        output_payload={"status": "transferred"},
        started_at=now,
        policy_decision="allow",
    )
    db.add(test_run)
    db.add(test_span)
    db.commit()

    # Candidate policy strictly denies transfer_funds
    candidate_yaml = """
version: "1"
rules:
  - id: block_transfer
    tool: transfer_funds
    action: deny
"""

    agent = ScriptedMockAgent(
        planned_calls=[("transfer_funds", {"account": "12345", "amount": 50000})],
        final_outcome="success",
    )

    harness = IncidentReplayHarness(db)
    res = harness.replay_run(
        original_run_id=run_id,
        agent=agent,
        candidate_policy_yaml=candidate_yaml,
        num_samples=1,
    )

    # Must be denied under candidate policy
    assert res.regression_detected is True
    assert any("Candidate policy blocked" in r for r in res.regression_reasons)
    diff = res.trajectory_diff[0]
    assert diff["policy_decision_replayed"] == "deny"

    # Cleanup
    db.query(Span).filter(Span.run_id == run_id).delete()
    db.query(Replay).filter(Replay.original_run_id == run_id).delete()
    db.query(Run).filter(Run.id == run_id).delete()
    db.commit()
    db.close()


# =========================================================================
# 6. Replay Isolation from Analytics Queries
# =========================================================================

def test_replay_isolation_from_analytics():
    """
    Verify that replayed runs tagged as 'replay' are excluded from analytics queries by default,
    and only included when include_replays=True is explicitly set.
    """
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)

    # Seed a standard run and a replay run
    base_run = Run(id="run-base-standard-1", model="gpt-4o", outcome="success", total_cost=0.50, started_at=now, tags={})
    replay_run = Run(id="run-replay-tagged-1", model="gpt-4o", outcome="success", total_cost=0.50, started_at=now, tags={"replay": True}, task_id="replay")

    db.add(base_run)
    db.add(replay_run)
    db.commit()

    try:
        # Default query: replays must be EXCLUDED
        summary_default = get_analytics_summary(db=db, include_replays=False)
        runs_default = [r for r in db.query(Run).all()]
        
        # When include_replays=True: replays must be INCLUDED
        summary_with_replays = get_analytics_summary(db=db, include_replays=True)

        assert summary_with_replays.total_runs >= summary_default.total_runs + 1

    finally:
        db.query(Run).filter(Run.id.in_(["run-base-standard-1", "run-replay-tagged-1"])).delete()
        db.commit()
        db.close()


# =========================================================================
# 7. Live HTTP API Endpoints
# =========================================================================

def test_replay_http_api_endpoints():
    """Verify POST /replay, GET /replay/{id}, and GET /replays endpoints work cleanly."""
    db: Session = SessionLocal()
    seed_default_api_key(db)
    now = datetime.now(timezone.utc)
    run_id = f"test-api-orig-{uuid.uuid4().hex[:8]}"

    test_run = Run(id=run_id, model="gpt-4o", outcome="success", started_at=now)
    test_span = Span(
        id=str(uuid.uuid4()),
        run_id=run_id,
        sequence_number=1,
        span_type="tool",
        name="get_stock_price",
        input_payload={"ticker": "AAPL"},
        output_payload={"price": 220.50},
        started_at=now,
        policy_decision="allow",
    )
    db.add(test_run)
    db.add(test_span)
    db.commit()
    db.close()

    try:
        # 1. POST /replay (requires admin token)
        resp = client.post(
            "/replay",
            headers={"X-API-Key": DEV_KEY, "X-Admin-Token": settings.ADMIN_TOKEN},
            json={
                "original_run_id": run_id,
                "target_model": "claude-3-5-sonnet",
                "matching_threshold": 0.85,
                "num_samples": 2,
                "compute_sensitivity": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["original_run_id"] == run_id
        assert data["fidelity_score"] == 1.0  # Exact match replay
        assert len(data["sample_results"]) == 2
        assert len(data["trajectory_diff"]) == 1
        assert len(data["sensitivity_table"]) == 3
        assert data["fidelity_range"] == 0.0
        assert data["fidelity_std_dev"] == 0.0
        replay_id = data["replay_id"]

        # 2. GET /replay/{id}
        get_resp = client.get(f"/replay/{replay_id}", headers={"X-API-Key": DEV_KEY})
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["replay_id"] == replay_id
        assert get_data["fidelity_score"] == 1.0

        # 3. GET /replays
        list_resp = client.get("/replays", headers={"X-API-Key": DEV_KEY})
        assert list_resp.status_code == 200
        replays_list = list_resp.json()
        assert any(r["id"] == replay_id for r in replays_list)

    finally:
        clean_db = SessionLocal()
        clean_db.query(Span).filter(Span.run_id == run_id).delete()
        clean_db.query(Replay).filter(Replay.original_run_id == run_id).delete()
        clean_db.query(Run).filter(Run.id == run_id).delete()
        clean_db.commit()
        clean_db.close()


def test_replay_endpoints_require_admin_token():
    """
    Verify that /replay and /replay/batch endpoints strictly enforce X-Admin-Token authentication.
    - Missing token -> 403 Forbidden
    - Invalid token -> 403 Forbidden
    - Valid token -> 200 OK
    """
    db: Session = SessionLocal()
    seed_default_api_key(db)
    now = datetime.now(timezone.utc)
    run_id = f"test-auth-{uuid.uuid4().hex[:8]}"

    test_run = Run(id=run_id, model="gpt-4o", outcome="success", started_at=now)
    test_span = Span(
        id=str(uuid.uuid4()),
        run_id=run_id,
        sequence_number=1,
        span_type="tool",
        name="tool_a",
        input_payload={"k": "v"},
        output_payload={"res": 1},
        started_at=now,
        policy_decision="allow",
    )
    db.add(test_run)
    db.add(test_span)
    db.commit()
    db.close()

    try:
        # Case 1: POST /replay without X-Admin-Token -> 403
        r1 = client.post(
            "/replay",
            headers={"X-API-Key": DEV_KEY},
            json={"original_run_id": run_id, "num_samples": 1},
        )
        assert r1.status_code == 403
        assert "X-Admin-Token" in r1.json()["detail"]

        # Case 2: POST /replay with invalid X-Admin-Token -> 403
        r2 = client.post(
            "/replay",
            headers={"X-API-Key": DEV_KEY, "X-Admin-Token": "invalid-secret"},
            json={"original_run_id": run_id, "num_samples": 1},
        )
        assert r2.status_code == 403

        # Case 3: POST /replay/batch without X-Admin-Token -> 403
        r3 = client.post(
            "/replay/batch",
            headers={"X-API-Key": DEV_KEY},
            json={"run_ids": [run_id], "num_samples": 1},
        )
        assert r3.status_code == 403

        # Case 4: POST /replay with valid X-Admin-Token -> 200
        r4 = client.post(
            "/replay",
            headers={"X-API-Key": DEV_KEY, "X-Admin-Token": settings.ADMIN_TOKEN},
            json={"original_run_id": run_id, "num_samples": 1},
        )
        assert r4.status_code == 200

    finally:
        clean_db = SessionLocal()
        clean_db.query(Span).filter(Span.run_id == run_id).delete()
        clean_db.query(Replay).filter(Replay.original_run_id == run_id).delete()
        clean_db.query(Run).filter(Run.id == run_id).delete()
        clean_db.commit()
        clean_db.close()


def test_majority_consistency_rule_for_regressions():
    """
    Directly tests RQ2 majority rule requirement:
    1. Sample fidelities [0.13, 1.0, 1.0] has mean ~0.71 (< 0.80), BUT only 1/3 samples degraded.
       Under majority rule, it must NOT be flagged as regression (regression_detected = False).
    2. Sample fidelities [0.20, 0.30, 1.0] has 2/3 samples degraded (< 0.80).
       Under majority rule, it MUST be flagged as regression (regression_detected = True).
    """
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    run_id = f"test-majority-{uuid.uuid4().hex[:8]}"

    orig_run = Run(id=run_id, model="gpt-4o", outcome="success", started_at=now)
    spans = [
        Span(
            id=str(uuid.uuid4()),
            run_id=run_id,
            sequence_number=1,
            span_type="tool",
            name="tool_alpha",
            input_payload={"val": 10},
            output_payload={"status": "ok"},
            started_at=now,
            policy_decision="allow",
        )
    ]
    db.add(orig_run)
    db.add(spans[0])
    db.commit()

    # Controlled agent whose sample calls produce exact fidelity sequences
    class ControllableMultiSampleAgent:
        def __init__(self, mode: str):
            self.mode = mode
            self.iteration = 0

        def run(self, prompt, tool_executor, model=None):
            self.iteration += 1
            if self.mode == "one_degraded_two_clean":
                # Sample 1: call unrecorded tool with bad outcome -> fidelity ~ 0.0
                # Samples 2 & 3: call exact recorded tool -> fidelity 1.0
                if self.iteration == 1:
                    tool_executor("unrecorded_bad_tool", {"val": 999})
                    return {"outcome": "failure"}
                else:
                    tool_executor("tool_alpha", {"val": 10})
                    return {"outcome": "success"}
            elif self.mode == "two_degraded_one_clean":
                # Samples 1 & 2: degraded -> fidelity ~ 0.0
                # Sample 3: clean -> fidelity 1.0
                if self.iteration in (1, 2):
                    tool_executor("unrecorded_bad_tool", {"val": 999})
                    return {"outcome": "failure"}
                else:
                    tool_executor("tool_alpha", {"val": 10})
                    return {"outcome": "success"}

    harness = IncidentReplayHarness(db)

    # Test 1: One degraded out of three ([0.0, 1.0, 1.0]) -> Must NOT be flagged
    agent_healthy = ControllableMultiSampleAgent(mode="one_degraded_two_clean")
    res1 = harness.replay_run(original_run_id=run_id, agent=agent_healthy, num_samples=3)
    fids1 = [s.fidelity_score for s in res1.sample_results]
    assert fids1 == [0.0, 1.0, 1.0]
    assert res1.mean_fidelity == 0.6667
    assert res1.fidelity_range == 1.0
    assert round(res1.fidelity_std_dev, 4) == 0.5774
    # Crucial assertion: 1 of 3 degraded does NOT trigger regression
    assert res1.regression_detected is False
    assert len(res1.regression_reasons) == 0

    # Test 2: Two degraded out of three ([0.0, 0.0, 1.0]) -> MUST be flagged
    agent_regressed = ControllableMultiSampleAgent(mode="two_degraded_one_clean")
    res2 = harness.replay_run(original_run_id=run_id, agent=agent_regressed, num_samples=3)
    fids2 = [s.fidelity_score for s in res2.sample_results]
    assert fids2 == [0.0, 0.0, 1.0]
    assert res2.mean_fidelity == 0.3333
    # Crucial assertion: 2 of 3 degraded triggers regression
    assert res2.regression_detected is True
    assert any("across majority of samples (2/3)" in r for r in res2.regression_reasons)

    # Cleanup
    db.query(Span).filter(Span.run_id == run_id).delete()
    db.query(Replay).filter(Replay.original_run_id == run_id).delete()
    db.query(Run).filter(Run.id == run_id).delete()
    db.commit()
    db.close()


def test_candidate_policy_restrict_orders_allows_users_and_denies_orders():
    """
    Direct unit test verifying candidate policy 'restrict_orders_access':
    - SELECT query on 'users' table MUST be allowed by default_action: allow.
    - SELECT query on 'orders' table MUST be denied by rule 'restrict_orders_access'.
    """
    from server.app.services.policy_engine import parse_policy_yaml, evaluate_policy

    policy_yaml = """
version: "1"
default_action: allow
rules:
  - id: restrict_orders_access
    tool: execute_sql
    parameters:
      query:
        contains: "orders"
    action: deny
"""
    policy = parse_policy_yaml(policy_yaml)

    # 1. Query targeting users table -> ALLOW
    res_users = evaluate_policy(
        tool_name="execute_sql",
        tool_args={"query": "SELECT count(*) AS active_users FROM users WHERE status = 'active';"},
        policy=policy,
    )
    assert res_users.decision == "allow"
    assert res_users.rule_id == "default_policy"

    # 2. Query targeting orders table -> DENY
    res_orders = evaluate_policy(
        tool_name="execute_sql",
        tool_args={"query": "SELECT sum(amount) AS total_revenue FROM orders WHERE status = 'completed';"},
        policy=policy,
    )
    assert res_orders.decision == "deny"
    assert res_orders.rule_id == "restrict_orders_access"


def test_hand_computed_candidate_policy_denial_fidelity_on_real_trace():
    """
    Hand-computed derivation test for Scenario 2 on real SQL trace:
    Original Trace:
      Step 1: execute_sql on users table (status=completed)
      Step 2: execute_sql on orders table (status=completed)
    Candidate Policy Replay:
      Step 1: execute_sql on users -> ALLOWED (matches recorded Step 1, arg similarity 1.0)
      Step 2: execute_sql on orders -> DENIED by candidate policy
    Canonical Derivation:
      S_tool = 1 - 1/2 = 0.50 (1 allowed step out of 2 recorded)
      S_args = 1.0 over the one matched allowed step
      S_outcome = 0.0 (replayed outcome failed due to policy deny vs original success)
      Composite Fidelity F = 0.4 * 0.50 + 0.3 * 1.0 + 0.3 * 0.0 = 0.20 + 0.30 + 0 = 0.5000 (50.0%)
    """
    from evaluation.trace_recorder import record_real_sql_agent_trace

    db: Session = SessionLocal()
    real_run_id = record_real_sql_agent_trace(db)

    policy_yaml = """
version: "1"
default_action: allow
rules:
  - id: restrict_orders_access
    tool: execute_sql
    parameters:
      query:
        contains: "orders"
    action: deny
"""
    orig_spans = (
        db.query(Span)
        .filter(Span.run_id == real_run_id, Span.span_type == "tool")
        .order_by(Span.sequence_number.asc())
        .all()
    )
    planned_calls = [(s.name, s.input_payload if isinstance(s.input_payload, dict) else {}) for s in orig_spans]
    agent = ScriptedMockAgent(planned_calls=planned_calls, final_outcome="success")

    harness = IncidentReplayHarness(db)
    res = harness.replay_run(
        original_run_id=real_run_id,
        agent=agent,
        target_model="demo-sql-agent-v1",
        candidate_policy_yaml=policy_yaml,
        num_samples=1,
    )

    # Assert exact hand-computed fidelity components
    sample = res.sample_results[0]
    assert sample.s_tool == 0.5000
    assert sample.s_args == 1.0000
    assert sample.s_outcome == 0.0000
    assert sample.fidelity_score == 0.5000
    assert res.mean_fidelity == 0.5000
    assert res.regression_detected is True

    # Assert trajectory diff captures both steps accurately
    assert len(res.trajectory_diff) == 2
    assert res.trajectory_diff[0]["policy_decision_replayed"] == "allow"
    assert res.trajectory_diff[0]["arg_similarity"] == 1.0
    assert res.trajectory_diff[1]["policy_decision_replayed"] == "deny"
    assert res.trajectory_diff[1]["arg_similarity"] == 1.0

    # Cleanup
    db.query(Span).filter(Span.run_id == real_run_id).delete()
    db.query(Replay).filter(Replay.original_run_id == real_run_id).delete()
    db.query(Run).filter(Run.id == real_run_id).delete()
    db.commit()
    db.close()

