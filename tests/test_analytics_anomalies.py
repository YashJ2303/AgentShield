import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from server.app.main import app
from server.app.database import get_db, SessionLocal
from server.app.models.run import Run
from server.app.models.span import Span
from server.app.services.pricing import calculate_cost, DEFAULT_PRICING
from server.app.services.anomaly_detector import (
    calculate_percentile,
    detect_repeated_tool_loops,
    detect_statistical_outliers,
)
from server.app.services.analytics_service import (
    categorize_failure,
    get_analytics_summary,
    get_breakdown_metrics,
    compare_models,
)

client = TestClient(app)


# =========================================================================
# 1. Hand-Computed Percentile Tests
# =========================================================================

def test_hand_computed_percentiles():
    """
    Hand-computed test:
    Dataset: [10.0, 20.0, 30.0, 40.0, 50.0]
    N = 5.
    p50: index (5-1) * 0.50 = 2.0 -> sorted[2] = 30.0
    p95: index (5-1) * 0.95 = 3.8 -> sorted[3] + 0.8 * (sorted[4] - sorted[3]) = 40.0 + 0.8 * 10.0 = 48.0
    """
    data = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert calculate_percentile(data, 50.0) == 30.0
    assert calculate_percentile(data, 95.0) == 48.0

    # Small samples
    assert calculate_percentile([], 50.0) == 0.0
    assert calculate_percentile([42.0], 50.0) == 42.0
    assert calculate_percentile([42.0], 95.0) == 42.0
    # 2 elements: index 1 * 0.5 = 0.5 -> 10 + 0.5 * 10 = 15.0
    assert calculate_percentile([10.0, 20.0], 50.0) == 15.0


# =========================================================================
# 2. Unknown Model in Pricing Table (Must Return None, Never $0)
# =========================================================================

def test_pricing_table_unknown_model_returns_none():
    """
    A model not in the pricing table must report cost as unknown (None), NEVER $0.00.
    Silent zeros falsely portray unmodeled models as free.
    """
    # Known model: gpt-4o ($2.50 / 1M prompt, $10.00 / 1M completion)
    # 1,000,000 prompt + 0 completion = exactly 2.50
    cost_gpt4o = calculate_cost("gpt-4o", 1_000_000, 0)
    assert cost_gpt4o == 2.50

    # Unknown model: must return None
    cost_unknown = calculate_cost("custom-finetuned-llama-70b", 10_000, 5_000)
    assert cost_unknown is None, f"Expected None for unknown model, got {cost_unknown}"

    # None model name: must return None
    assert calculate_cost(None, 1000, 1000) is None


# =========================================================================
# 3. Hand-Computed Completion Rate & Cost per Successful Task
# =========================================================================

def test_hand_computed_completion_rate_and_cost_per_success():
    """
    Hand-computed test:
    Runs:
      R1: outcome='success', cost=0.03
      R2: outcome='success', cost=0.01
      R3: outcome='failed', cost=0.02
      R4: outcome='blocked', cost=0.01
      R5: outcome='timed_out', cost=0.01
    Total runs n = 5
    Successful runs = 2 (blocked and timed_out are strictly NOT success)
    Completion rate = 2 / 5 = 0.40 (40.0%)
    Total cost = 0.08
    Cost per run = 0.08 / 5 = 0.016
    Cost per successful task = 0.08 / 2 = 0.040
    """
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    test_runs = [
        Run(id="hc-run-1", model="hc-model", outcome="success", total_cost=0.03, latency_ms=500, started_at=now),
        Run(id="hc-run-2", model="hc-model", outcome="success", total_cost=0.01, latency_ms=600, started_at=now),
        Run(id="hc-run-3", model="hc-model", outcome="failed", total_cost=0.02, latency_ms=700, started_at=now),
        Run(id="hc-run-4", model="hc-model", outcome="blocked", total_cost=0.01, latency_ms=800, started_at=now),
        Run(id="hc-run-5", model="hc-model", outcome="timed_out", total_cost=0.01, latency_ms=900, started_at=now),
    ]
    try:
        db.add_all(test_runs)
        db.commit()

        summary = get_analytics_summary(db, model="hc-model")
        assert summary.total_runs == 5
        assert summary.successful_runs == 2
        assert summary.task_completion_rate == 0.40
        assert summary.total_cost == 0.08
        assert summary.cost_per_run == 0.016
        assert summary.cost_per_successful_task == 0.040

    finally:
        db.query(Run).filter(Run.model == "hc-model").delete(synchronize_session=False)
        db.commit()
        db.close()


def test_division_by_zero_guard_when_zero_successes():
    """When there are 0 successful runs, cost_per_successful_task must be None without raising ZeroDivisionError."""
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    test_runs = [
        Run(id="zero-succ-1", model="zero-succ-model", outcome="failed", total_cost=0.05, latency_ms=400, started_at=now),
        Run(id="zero-succ-2", model="zero-succ-model", outcome="blocked", total_cost=0.03, latency_ms=500, started_at=now),
    ]
    try:
        db.add_all(test_runs)
        db.commit()

        summary = get_analytics_summary(db, model="zero-succ-model")
        assert summary.total_runs == 2
        assert summary.successful_runs == 0
        assert summary.task_completion_rate == 0.0
        assert summary.cost_per_successful_task is None  # Guarded: No division by zero

    finally:
        db.query(Run).filter(Run.model == "zero-succ-model").delete(synchronize_session=False)
        db.commit()
        db.close()


# =========================================================================
# 4. Hand-Computed IQR Outlier Math & Minimum Sample Size
# =========================================================================

def test_hand_computed_iqr_outliers():
    """
    Hand-computed test:
    Latencies: [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 5000.0]
    n = 9.
    Sorted: [100, 200, 300, 400, 500, 600, 700, 800, 5000]
    Q1: index (9-1) * 0.25 = 2.0 -> 300.0
    Q3: index (9-1) * 0.75 = 6.0 -> 700.0
    IQR: 700.0 - 300.0 = 400.0
    Threshold (1.5 * IQR): 700.0 + 1.5 * 400.0 = 1300.0
    Extreme Threshold (3.0 * IQR): 700.0 + 3.0 * 400.0 = 1900.0
    Run with 5000.0 exceeds 1900.0 -> Must be flagged with severity='critical'
    """
    class MockRun:
        def __init__(self, run_id, latency_ms, step_count=3, total_cost=0.01):
            self.id = run_id
            self.latency_ms = latency_ms
            self.step_count = step_count
            self.total_cost = total_cost
            self.started_at = datetime.now(timezone.utc)

    latencies = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 5000.0]
    runs = [MockRun(f"iqr-run-{i}", lat) for i, lat in enumerate(latencies)]

    anomalies = detect_statistical_outliers(runs, min_sample_size=5)
    assert len(anomalies) == 1
    outlier = anomalies[0]
    assert outlier["run_id"] == "iqr-run-8"
    assert outlier["value"] == 5000
    assert outlier["severity"] == "critical"
    assert outlier["sample_size"] == 9
    assert "Threshold=1300.0" in outlier["baseline_reference"]


def test_outlier_minimum_sample_size_guard():
    """Anomalies must not be flagged if sample size n < min_sample_size (e.g. n=3)."""
    class MockRun:
        def __init__(self, run_id, latency_ms):
            self.id = run_id
            self.latency_ms = latency_ms
            self.step_count = 3
            self.total_cost = 0.01
            self.started_at = datetime.now(timezone.utc)

    # Sample size of only 3 runs (below min_sample_size=5)
    small_runs = [MockRun("r1", 100), MockRun("r2", 200), MockRun("r3", 10000)]
    anomalies = detect_statistical_outliers(small_runs, min_sample_size=5)
    assert len(anomalies) == 0, "Outlier detector must guard against small samples (n < 5)"


# =========================================================================
# 5. Loop Detection: Positive and Negative Cases
# =========================================================================

def test_loop_detection_positive_and_negative():
    """
    Test exact definition: same tool + same canonical arguments N times consecutively (default N=3).
    """
    class MockSpan:
        def __init__(self, name, input_payload, seq):
            self.span_type = "tool"
            self.name = name
            self.input_payload = input_payload
            self.sequence_number = seq
            self.started_at = datetime.now(timezone.utc)

    # Positive Case 1: 3 identical calls to web_search with identical arguments
    spans_pos1 = [
        MockSpan("web_search", {"q": "news"}, 1),
        MockSpan("web_search", {"q": "news"}, 2),
        MockSpan("web_search", {"q": "news"}, 3),
    ]
    loops1 = detect_repeated_tool_loops(spans_pos1, "run-loop-pos1", threshold_consecutive=3)
    assert len(loops1) == 1
    assert loops1[0]["value"] == 3
    assert loops1[0]["type"] == "repeated_tool_loop"

    # Positive Case 2: Number canonicalization (250000 and 250000.0) detected as loop
    spans_pos2 = [
        MockSpan("wire_transfer", {"amount": 250000}, 1),
        MockSpan("wire_transfer", {"amount": 250000.0}, 2),
        MockSpan("wire_transfer", {"amount": 250000}, 3),
    ]
    loops2 = detect_repeated_tool_loops(spans_pos2, "run-loop-pos2", threshold_consecutive=3)
    assert len(loops2) == 1

    # Negative Case 1: Only 2 identical calls (below N=3 threshold)
    spans_neg1 = [
        MockSpan("web_search", {"q": "news"}, 1),
        MockSpan("web_search", {"q": "news"}, 2),
        MockSpan("fetch_url", {"url": "news.com"}, 3),
    ]
    loops_neg1 = detect_repeated_tool_loops(spans_neg1, "run-loop-neg1", threshold_consecutive=3)
    assert len(loops_neg1) == 0

    # Negative Case 2: 3 calls with varying arguments (pagination)
    spans_neg2 = [
        MockSpan("fetch_page", {"page": 1}, 1),
        MockSpan("fetch_page", {"page": 2}, 2),
        MockSpan("fetch_page", {"page": 3}, 3),
    ]
    loops_neg2 = detect_repeated_tool_loops(spans_neg2, "run-loop-neg2", threshold_consecutive=3)
    assert len(loops_neg2) == 0


# =========================================================================
# 6. Failure Categorization Deterministic Priority
# =========================================================================

def test_failure_categorization_rules():
    """Verify failure categorization follows the deterministic rule hierarchy."""
    class MockRun:
        def __init__(self, error_message, failure_category=None):
            self.id = "cat-run-id"
            self.error_message = error_message
            self.failure_category = failure_category

    class MockSpan:
        def __init__(self, span_type="tool", policy_decision=None, error=None, name="tool"):
            self.span_type = span_type
            self.policy_decision = policy_decision
            self.error = error
            self.name = name
            self.input_payload = {}
            self.sequence_number = 1
            self.started_at = datetime.now(timezone.utc)

    # 1. policy_block
    r_pol = MockRun("Blocked by security check")
    assert categorize_failure(r_pol, [MockSpan(policy_decision="deny")]) == "policy_block"

    # 2. budget_exceeded
    r_bud = MockRun("Run exceeded budget: cost limit of $0.50 breached")
    assert categorize_failure(r_bud, []) == "budget_exceeded"

    # 3. timeout
    r_time = MockRun("Execution deadline exceeded: timeout waiting for response")
    assert categorize_failure(r_time, []) == "timeout"

    # 4. loop
    r_loop = MockRun("Maximum recursion depth exceeded in agent loop")
    assert categorize_failure(r_loop, []) == "loop"

    # 5. malformed_output
    r_mal = MockRun("JSONDecodeError: Unterminated string")
    assert categorize_failure(r_mal, []) == "malformed_output"

    # 6. tool_error
    r_tool = MockRun("Subprocess error")
    assert categorize_failure(r_tool, [MockSpan(error="Exit code 1")]) == "tool_error"

    # 7. other
    r_oth = MockRun("Generic unclassified failure")
    assert categorize_failure(r_oth, []) == "other"


# =========================================================================
# 7. Model Comparison Endpoint with Sample Sizes
# =========================================================================

# =========================================================================
# 7. Model Comparison Endpoint with Insufficient Data Guard (n < 20)
# =========================================================================

def test_model_comparison_insufficient_data_guard():
    """
    If either side has n < 20 runs, compare_models must declare winner = 'insufficient_data'
    while still reporting the raw values and diff percentage accurately.
    When both sides reach n >= 20, an actual winner (or tie) is declared.
    """
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    # n = 4 per side (below n=20 threshold)
    runs_a_small = [
        Run(id=f"cmp-a-small-{i}", model="model-alpha", outcome="success", total_cost=0.01, latency_ms=800, started_at=now)
        for i in range(4)
    ]
    runs_b_small = [
        Run(id=f"cmp-b-small-{i}", model="model-beta", outcome="success" if i < 2 else "failure", total_cost=0.02, latency_ms=1200, started_at=now)
        for i in range(4)
    ]
    try:
        db.add_all(runs_a_small + runs_b_small)
        db.commit()

        cmp_res = compare_models(db, "model-alpha", "model-beta")
        assert cmp_res.model_a == "model-alpha"
        assert cmp_res.model_b == "model-beta"
        assert cmp_res.model_a_sample_size == 4
        assert cmp_res.model_b_sample_size == 4
        assert "insufficient_data" in (cmp_res.note or "")

        # Raw values are preserved, but winner is 'insufficient_data' due to n=4 < 20
        comp_rate_metric = next(m for m in cmp_res.metrics if m.metric_name == "Task Completion Rate")
        assert comp_rate_metric.model_a_value == 1.0
        assert comp_rate_metric.model_b_value == 0.5
        assert comp_rate_metric.diff_percentage == -50.0
        assert comp_rate_metric.winner == "insufficient_data"

        for m in cmp_res.metrics:
            assert m.winner == "insufficient_data"

    finally:
        db.query(Run).filter(Run.id.like("cmp-%")).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_model_comparison_winner_when_n_sufficient():
    """Verify that when both sides have n >= 20, winners are evaluated properly."""
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    # n = 20 per side
    runs_a = [
        Run(id=f"cmp-big-a-{i}", model="model-alpha-big", outcome="success", total_cost=0.01, latency_ms=800, started_at=now)
        for i in range(20)
    ]
    runs_b = [
        Run(id=f"cmp-big-b-{i}", model="model-beta-big", outcome="success" if i < 10 else "failure", total_cost=0.02, latency_ms=1200, started_at=now)
        for i in range(20)
    ]
    try:
        db.add_all(runs_a + runs_b)
        db.commit()

        cmp_res = compare_models(db, "model-alpha-big", "model-beta-big")
        assert cmp_res.model_a_sample_size == 20
        assert cmp_res.model_b_sample_size == 20

        comp_rate_metric = next(m for m in cmp_res.metrics if m.metric_name == "Task Completion Rate")
        assert comp_rate_metric.model_a_value == 1.0
        assert comp_rate_metric.model_b_value == 0.5
        assert comp_rate_metric.winner == "model_a"

    finally:
        db.query(Run).filter(Run.id.like("cmp-big-%")).delete(synchronize_session=False)
        db.commit()
        db.close()


# =========================================================================
# 8. Stored Failure Categories Strictly Enforced
# =========================================================================

def test_stored_failure_categories_strictly_valid():
    """Verify every stored failure_category belongs to the 7 valid spec categories."""
    from server.app.services.analytics_service import VALID_FAILURE_CATEGORIES
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    test_runs = [
        Run(id="cat-v-1", model="test-m", outcome="failure", error_message="OperationalError: database locked", started_at=now),
        Run(id="cat-v-2", model="test-m", outcome="blocked", error_message="prohibited SQL", started_at=now),
        Run(id="cat-v-3", model="test-m", outcome="timed_out", error_message="deadline exceeded", started_at=now),
        Run(id="cat-v-4", model="test-m", outcome="failure", error_message="budget cost limit breached", started_at=now),
        Run(id="cat-v-5", model="test-m", outcome="failure", error_message="JSONDecodeError: invalid json", started_at=now),
    ]
    try:
        db.add_all(test_runs)
        db.commit()

        # Run summary to trigger categorization and database persistence
        summary = get_analytics_summary(db)
        assert summary.total_runs > 0

        # Query all runs in DB with non-null failure_category
        persisted_runs = db.query(Run).filter(Run.failure_category.isnot(None)).all()
        for r in persisted_runs:
            assert r.failure_category in VALID_FAILURE_CATEGORIES, (
                f"Run {r.id} stored invalid category '{r.failure_category}' not in {VALID_FAILURE_CATEGORIES}"
            )

    finally:
        db.query(Run).filter(Run.id.like("cat-v-%")).delete(synchronize_session=False)
        db.commit()
        db.close()


# =========================================================================
# 9. Outlier Baselines Computed Per Task Type
# =========================================================================

def test_iqr_outliers_computed_per_task_type():
    """
    Verify IQR outlier baselines are computed per task_id group.
    A 2,000ms latency is completely normal for a 'web_agent' task,
    and must not flag a 60ms 'sql_agent' run as anomalous.
    """
    from server.app.services.analytics_service import get_all_anomalies
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)

    # 6 runs for sql_agent with low latency (40-60ms) + 1 extreme outlier (900ms)
    sql_runs = [
        Run(id=f"sql-task-run-{i}", task_id="sql_agent", model="gpt-4o", outcome="success", total_cost=0.001, latency_ms=50 + i * 2, step_count=2, started_at=now)
        for i in range(6)
    ]
    sql_outlier = Run(id="sql-task-outlier", task_id="sql_agent", model="gpt-4o", outcome="success", total_cost=0.01, latency_ms=900, step_count=2, started_at=now)

    # 6 runs for web_agent with high baseline latency (2000-2500ms)
    web_runs = [
        Run(id=f"web-task-run-{i}", task_id="web_agent", model="gpt-4o", outcome="success", total_cost=0.05, latency_ms=2000 + i * 50, step_count=10, started_at=now)
        for i in range(6)
    ]

    try:
        db.add_all(sql_runs + [sql_outlier] + web_runs)
        db.commit()

        anomalies = get_all_anomalies(db)
        
        # The sql_outlier (900ms) should be flagged within task:sql_agent
        sql_anomalies = [a for a in anomalies if a.get("run_id") == "sql-task-outlier"]
        assert len(sql_anomalies) > 0, "Expected sql-task-outlier (900ms) to be detected within sql_agent task baseline"
        assert "task:sql_agent" in sql_anomalies[0]["message"]

        # The normal web_agent runs (2000ms) must NOT cause normal sql runs (50ms) to look like anomalies
        normal_sql_flagged = [a for a in anomalies if a.get("run_id") in [r.id for r in sql_runs]]
        assert len(normal_sql_flagged) == 0, f"Normal SQL runs were falsely flagged: {normal_sql_flagged}"

    finally:
        db.query(Run).filter(Run.id.like("sql-task-%")).delete(synchronize_session=False)
        db.query(Run).filter(Run.id.like("web-task-%")).delete(synchronize_session=False)
        db.commit()
        db.close()


# =========================================================================
# 10. Privacy Check: /approvals/{id}/consume Does Not Store or Log Raw Args
# =========================================================================

def test_consume_approval_does_not_store_or_log_raw_args(caplog):
    """
    Verify /approvals/{id}/consume receives raw arguments to verify call_hash,
    but never writes them to the DB or outputs them into structured logs.
    """
    import logging
    from server.app.models.approval import Approval
    from server.app.services.approval_manager import compute_call_hash

    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    app_id = "test-priv-app-001"
    run_id = "test-priv-run-001"
    tool_name = "secret_payment_tool"
    secret_args = {"account_number": "1234-SECRET-9999", "secret_key": "raw_sensitive_password_xyz"}
    call_hash = compute_call_hash(run_id, tool_name, secret_args)

    approval = Approval(
        id=app_id,
        run_id=run_id,
        tool_name=tool_name,
        tool_args={"account_number": "[REDACTED]"}, # Stored redacted
        call_hash=call_hash,
        status="approved",
        is_consumed=0,
        requested_at=now,
    )
    try:
        db.add(approval)
        db.commit()

        with caplog.at_level(logging.DEBUG):
            consume_resp = client.post(
                f"/approvals/{app_id}/consume",
                json={
                    "run_id": run_id,
                    "tool_name": tool_name,
                    "tool_args": secret_args,
                },
            )
            assert consume_resp.status_code == 200
            assert consume_resp.json()["valid"] is True

        # Check DB: is_consumed is 1, but secret_key is nowhere in approval record
        db.expire_all()
        persisted = db.query(Approval).filter(Approval.id == app_id).first()
        assert persisted.is_consumed == 1
        assert "raw_sensitive_password_xyz" not in str(persisted.tool_args)

        # Check captured logs: raw argument must not appear anywhere
        for record in caplog.records:
            assert "raw_sensitive_password_xyz" not in record.getMessage()

    finally:
        db.query(Approval).filter(Approval.id == app_id).delete(synchronize_session=False)
        db.commit()
        db.close()


# =========================================================================
# 11. Analytics API Endpoints Live Test
# =========================================================================

def test_analytics_api_endpoints_live():
    """Verify live HTTP endpoints /analytics/summary, /analytics/breakdown, and /analytics/anomalies."""
    summary_resp = client.get("/analytics/summary")
    assert summary_resp.status_code == 200
    s_data = summary_resp.json()
    assert "total_runs" in s_data
    assert "task_completion_rate" in s_data
    assert "p50_latency_ms" in s_data

    breakdown_resp = client.get("/analytics/breakdown")
    assert breakdown_resp.status_code == 200
    b_data = breakdown_resp.json()
    assert "models" in b_data
    assert "tools" in b_data
    assert "prompt_versions" in b_data
    assert "time_series" in b_data

    # Every time-series bucket must expose the per-day counters used by the
    # Command Center sparklines, and those counters must be consistent with the
    # aggregate summary (same window, no filters).
    ts_total_tool_calls = 0
    ts_total_blocked = 0
    for bucket in b_data["time_series"]:
        assert "tool_calls" in bucket
        assert "blocked_runs" in bucket
        assert isinstance(bucket["tool_calls"], int)
        assert isinstance(bucket["blocked_runs"], int)
        ts_total_tool_calls += bucket["tool_calls"]
        ts_total_blocked += bucket["blocked_runs"]

    assert ts_total_tool_calls == s_data["total_tool_calls"]
    assert ts_total_blocked == s_data["blocked_runs"]

    # Tool breakdown must report the denying rule for blocked tools.
    for tool in b_data["tools"]:
        assert "top_block_rule" in tool
        if tool["top_block_rule"] is not None:
            assert tool["policy_block_count"] > 0

    anomalies_resp = client.get("/analytics/anomalies")
    assert anomalies_resp.status_code == 200
    assert isinstance(anomalies_resp.json(), list)


# =========================================================================
# 12. Breakdown: per-day counters + top denying rule
# =========================================================================

def test_breakdown_tool_calls_and_top_block_rule():
    """
    The Command Center derives its sparklines and denial-attribution table from
    /analytics/breakdown. Verify the service computes, from real spans:
      - per-day tool_calls / blocked_runs
      - the most frequent denying rule per tool (mode over denied spans)
    """
    db: Session = SessionLocal()
    task_id = "cc-breakdown-test-task"
    day = datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc)
    run_ids = ["cc-bd-run-1", "cc-bd-run-2"]

    runs = [
        Run(id=run_ids[0], task_id=task_id, model="cc-model", outcome="success",
            total_cost=0.0, latency_ms=10, started_at=day),
        Run(id=run_ids[1], task_id=task_id, model="cc-model", outcome="blocked",
            total_cost=0.0, latency_ms=20, started_at=day),
    ]
    spans = [
        Span(id="cc-bd-span-1", run_id=run_ids[0], sequence_number=1, span_type="tool",
             name="cc_tool", policy_decision="allow", started_at=day),
        Span(id="cc-bd-span-2", run_id=run_ids[0], sequence_number=2, span_type="tool",
             name="cc_tool", policy_decision="deny", policy_rule_id="rule_y", started_at=day),
        Span(id="cc-bd-span-3", run_id=run_ids[1], sequence_number=1, span_type="tool",
             name="cc_tool", policy_decision="deny", policy_rule_id="rule_x", started_at=day),
        Span(id="cc-bd-span-4", run_id=run_ids[1], sequence_number=2, span_type="tool",
             name="cc_tool", policy_decision="deny", policy_rule_id="rule_x", started_at=day),
    ]

    try:
        db.add_all(runs)
        db.add_all(spans)
        db.commit()

        breakdown = get_breakdown_metrics(db, task_id=task_id)

        tool = next(t for t in breakdown["tools"] if t.tool_name == "cc_tool")
        assert tool.sample_size == 4
        assert tool.policy_block_count == 3
        # rule_x denied twice, rule_y once -> rule_x is the modal rule
        assert tool.top_block_rule == "rule_x"

        assert len(breakdown["time_series"]) == 1
        bucket = breakdown["time_series"][0]
        assert bucket.date == "2026-03-04"
        assert bucket.sample_size == 2
        assert bucket.tool_calls == 4
        assert bucket.blocked_runs == 1

    finally:
        db.query(Span).filter(Span.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(Run).filter(Run.task_id == task_id).delete(synchronize_session=False)
        db.commit()
        db.close()

