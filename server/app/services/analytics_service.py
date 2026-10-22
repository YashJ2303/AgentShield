from typing import Optional, Any
from datetime import datetime, timezone
import statistics
from collections import Counter, defaultdict
from sqlalchemy.orm import Session

from server.app.models.run import Run
from server.app.models.span import Span
from server.app.schemas.analytics import (
    AnalyticsSummaryResponse,
    ModelBreakdownItem,
    ToolBreakdownItem,
    PromptVersionBreakdownItem,
    TimeSeriesDataPoint,
    ModelComparisonResponse,
    ModelComparisonMetric,
    AnomalyItem,
)
from server.app.services.anomaly_detector import (
    calculate_percentile,
    detect_repeated_tool_loops,
    detect_statistical_outliers,
)


VALID_FAILURE_CATEGORIES = (
    "tool_error",
    "policy_block",
    "timeout",
    "loop",
    "malformed_output",
    "budget_exceeded",
    "other",
)


def categorize_failure(run: Run, spans: list[Span]) -> str:
    """
    Classify the root cause of an unsuccessful run into a standardized category.
    Priority order:
    1. policy_block
    2. budget_exceeded
    3. timeout
    4. loop
    5. malformed_output
    6. tool_error
    7. other
    """
    err_str = (run.error_message or "").lower()

    # 1. Policy block check
    if getattr(run, "outcome", None) == "blocked":
        return "policy_block"
    for s in spans:
        if s.policy_decision in ("deny", "rejected"):
            return "policy_block"
    if any(k in err_str for k in ("policy", "blocked", "denied", "prohibited", "not permitted")):
        return "policy_block"

    # 2. Budget exceeded check
    if any(k in err_str for k in ("budget", "cost limit", "token limit", "step limit", "wall time limit")):
        return "budget_exceeded"

    # 3. Timeout check
    if getattr(run, "outcome", None) == "timed_out" or any(k in err_str for k in ("timeout", "timed out", "timed_out", "deadline")):
        return "timeout"

    # 4. Loop detection check
    loop_anomalies = detect_repeated_tool_loops(spans, run.id)
    if loop_anomalies or any(k in err_str for k in ("loop", "recursion", "maximum iterations")):
        return "loop"

    # 5. Malformed output
    if any(k in err_str for k in ("json", "parse", "malformed", "schema", "validation")):
        return "malformed_output"

    # 6. Tool execution error
    for s in spans:
        if s.span_type == "tool" and s.error:
            return "tool_error"
    if "tool" in err_str or "exit code" in err_str:
        return "tool_error"

    return "other"


def _filter_runs_query(
    runs: list[Run],
    tag: Optional[str] = None,
    experiment_id: Optional[str] = None,
    include_replays: bool = False,
) -> list[Run]:
    """Helper to filter runs by tag or experiment_id, excluding replay runs by default."""
    filtered = runs
    if not include_replays:
        filtered = [
            r for r in filtered
            if not (isinstance(r.tags, dict) and (r.tags.get("replay") is True or r.tags.get("tag") == "replay"))
            and r.task_id != "replay"
        ]
    if tag:
        k, *v = tag.split(":", 1)
        if v:
            filtered = [r for r in filtered if isinstance(r.tags, dict) and str(r.tags.get(k)) == v[0]]
        else:
            filtered = [r for r in filtered if isinstance(r.tags, dict) and k in r.tags]
    if experiment_id:
        filtered = [
            r for r in filtered
            if r.task_id == experiment_id or (isinstance(r.tags, dict) and r.tags.get("experiment_id") == experiment_id)
        ]
    return filtered


def get_analytics_summary(
    db: Session,
    model: Optional[str] = None,
    prompt_version: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    tag: Optional[str] = None,
    experiment_id: Optional[str] = None,
    task_id: Optional[str] = None,
    include_replays: bool = False,
) -> AnalyticsSummaryResponse:
    query = db.query(Run)
    if model:
        query = query.filter(Run.model == model)
    if prompt_version:
        query = query.filter(Run.prompt_version == prompt_version)
    if task_id:
        query = query.filter(Run.task_id == task_id)
    if start_date:
        query = query.filter(Run.started_at >= start_date)
    if end_date:
        query = query.filter(Run.started_at <= end_date)

    raw_runs: list[Run] = query.all()
    runs = _filter_runs_query(raw_runs, tag=tag, experiment_id=experiment_id, include_replays=include_replays)
    total_runs = len(runs)
    if total_runs == 0:
        return AnalyticsSummaryResponse()

    # Definition of success: outcome == 'success' strictly
    successful_runs = sum(1 for r in runs if r.outcome == "success")
    blocked_runs = sum(1 for r in runs if r.outcome == "blocked")
    timed_out_runs = sum(1 for r in runs if r.outcome == "timed_out")
    # Mutually exclusive: failed_runs are non-success runs that are not blocked or timed out
    failed_runs = sum(1 for r in runs if r.outcome in ("failure", "failed"))

    task_completion_rate = round(successful_runs / total_runs, 4)

    # Cost calculations (handling null / unknown costs safely)
    known_costs = [r.total_cost for r in runs if r.total_cost is not None]
    total_cost = round(sum(known_costs), 6) if known_costs else None
    
    cost_per_run = round(total_cost / total_runs, 6) if (total_cost is not None and total_runs > 0) else None
    # Guard against division by zero in cost_per_successful_task
    cost_per_successful_task = (
        round(total_cost / successful_runs, 6)
        if (total_cost is not None and successful_runs > 0)
        else None
    )

    total_tokens = sum(r.total_tokens for r in runs if r.total_tokens is not None)
    prompt_tokens = sum(r.prompt_tokens for r in runs if r.prompt_tokens is not None)
    completion_tokens = sum(r.completion_tokens for r in runs if r.completion_tokens is not None)
    avg_tokens_per_run = round(total_tokens / total_runs, 1)

    latencies = [float(r.latency_ms) for r in runs if r.latency_ms is not None]
    p50_latency_ms = round(calculate_percentile(latencies, 50.0), 2)
    p95_latency_ms = round(calculate_percentile(latencies, 95.0), 2)
    avg_latency_ms = round(statistics.mean(latencies), 2) if latencies else 0.0

    # Query spans for runs
    run_ids = [r.id for r in runs]
    all_spans: list[Span] = db.query(Span).filter(Span.run_id.in_(run_ids)).all() if run_ids else []
    
    spans_by_run = defaultdict(list)
    for s in all_spans:
        spans_by_run[s.run_id].append(s)

    tool_spans = [s for s in all_spans if s.span_type == "tool"]
    total_tool_calls = len(tool_spans)
    tool_errors = sum(1 for s in tool_spans if s.error)
    tool_error_rate = round(tool_errors / total_tool_calls, 4) if total_tool_calls > 0 else 0.0

    # Calculate retry rate: consecutive calls to the same tool in a run
    retry_count = 0
    for r_id, r_spans in spans_by_run.items():
        t_spans = [s for s in r_spans if s.span_type == "tool"]
        t_spans.sort(key=lambda s: getattr(s, "sequence_number", 0))
        for i in range(1, len(t_spans)):
            if t_spans[i].name == t_spans[i - 1].name:
                retry_count += 1
    retry_rate = round(retry_count / total_tool_calls, 4) if total_tool_calls > 0 else 0.0

    # Failure categories strictly constrained to the 7 valid categories
    failure_categories: dict[str, int] = {cat: 0 for cat in VALID_FAILURE_CATEGORIES}

    updated_any = False
    for r in runs:
        if r.outcome != "success":
            cat = categorize_failure(r, spans_by_run[r.id])
            failure_categories[cat] += 1
            if r.failure_category != cat:
                r.failure_category = cat
                updated_any = True

    if updated_any:
        try:
            db.commit()
        except Exception:
            db.rollback()

    # Keep only active categories with count > 0
    active_failure_categories = {k: v for k, v in failure_categories.items() if v > 0}

    policy_block_rate = round(blocked_runs / total_runs, 4) if total_runs > 0 else 0.0

    return AnalyticsSummaryResponse(
        total_runs=total_runs,
        successful_runs=successful_runs,
        failed_runs=failed_runs,
        blocked_runs=blocked_runs,
        timed_out_runs=timed_out_runs,
        task_completion_rate=task_completion_rate,
        total_cost=total_cost,
        cost_per_run=cost_per_run,
        cost_per_successful_task=cost_per_successful_task,
        total_tokens=total_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        avg_tokens_per_run=avg_tokens_per_run,
        p50_latency_ms=p50_latency_ms,
        p95_latency_ms=p95_latency_ms,
        avg_latency_ms=avg_latency_ms,
        total_tool_calls=total_tool_calls,
        tool_error_rate=tool_error_rate,
        repeat_call_rate=retry_rate,
        retry_rate=retry_rate,
        policy_block_rate=policy_block_rate,
        failure_categories=active_failure_categories,
    )


def get_breakdown_metrics(
    db: Session,
    tag: Optional[str] = None,
    experiment_id: Optional[str] = None,
    task_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    include_replays: bool = False,
) -> dict[str, Any]:
    query = db.query(Run)
    if task_id:
        query = query.filter(Run.task_id == task_id)
    if start_date:
        query = query.filter(Run.started_at >= start_date)
    if end_date:
        query = query.filter(Run.started_at <= end_date)

    raw_runs: list[Run] = query.all()
    runs = _filter_runs_query(raw_runs, tag=tag, experiment_id=experiment_id, include_replays=include_replays)

    run_ids = [r.id for r in runs]
    spans: list[Span] = db.query(Span).filter(Span.run_id.in_(run_ids)).all() if run_ids else []

    # 1. Model breakdown
    models_dict: dict[str, list[Run]] = defaultdict(list)
    for r in runs:
        m_name = r.model or "unknown"
        models_dict[m_name].append(r)

    model_breakdown: list[ModelBreakdownItem] = []
    for m_name, m_runs in sorted(models_dict.items()):
        cnt = len(m_runs)
        succ = sum(1 for r in m_runs if r.outcome == "success")
        known_c = [r.total_cost for r in m_runs if r.total_cost is not None]
        t_cost = round(sum(known_c), 6) if known_c else None
        
        cost_per_run = round(t_cost / cnt, 6) if (t_cost is not None and cnt > 0) else None
        cost_per_succ = round(t_cost / succ, 6) if (t_cost is not None and succ > 0) else None

        t_tok = sum(r.total_tokens for r in m_runs if r.total_tokens is not None)
        lats = [float(r.latency_ms) for r in m_runs if r.latency_ms is not None]
        p50_lat = round(calculate_percentile(lats, 50.0), 2)
        p95_lat = round(calculate_percentile(lats, 95.0), 2)
        avg_lat = round(statistics.mean(lats), 2) if lats else 0.0

        model_breakdown.append(
            ModelBreakdownItem(
                model=m_name,
                sample_size=cnt,
                completion_rate=round(succ / cnt, 4) if cnt > 0 else 0.0,
                total_cost=t_cost,
                cost_per_run=cost_per_run,
                cost_per_successful_task=cost_per_succ,
                p50_latency_ms=p50_lat,
                p95_latency_ms=p95_lat,
                avg_latency_ms=avg_lat,
                total_tokens=t_tok,
            )
        )

    # 2. Tool breakdown
    tools_dict: dict[str, list[Span]] = defaultdict(list)
    for s in spans:
        if s.span_type == "tool":
            tools_dict[s.name].append(s)

    tool_breakdown: list[ToolBreakdownItem] = []
    for t_name, t_spans in sorted(tools_dict.items()):
        cnt = len(t_spans)
        errs = sum(1 for s in t_spans if s.error)
        blocks = sum(1 for s in t_spans if s.policy_decision in ("deny", "rejected"))
        lats = [float(s.latency_ms) for s in t_spans if s.latency_ms is not None]
        p50_lat = round(calculate_percentile(lats, 50.0), 2)
        p95_lat = round(calculate_percentile(lats, 95.0), 2)
        avg_lat = round(statistics.mean(lats), 2) if lats else 0.0

        # Compute retry count within tool calls
        t_spans_sorted = sorted(t_spans, key=lambda s: getattr(s, "started_at", datetime.min))
        retries = 0
        for i in range(1, len(t_spans_sorted)):
            if t_spans_sorted[i].run_id == t_spans_sorted[i - 1].run_id:
                retries += 1

        # Most frequent denying rule for this tool (None when never blocked)
        block_rules = [
            s.policy_rule_id
            for s in t_spans
            if s.policy_decision in ("deny", "rejected") and s.policy_rule_id
        ]
        top_block_rule = Counter(block_rules).most_common(1)[0][0] if block_rules else None

        tool_breakdown.append(
            ToolBreakdownItem(
                tool_name=t_name,
                sample_size=cnt,
                error_count=errs,
                error_rate=round(errs / cnt, 4) if cnt > 0 else 0.0,
                repeat_call_count=retries,
                repeat_call_rate=round(retries / cnt, 4) if cnt > 0 else 0.0,
                retry_count=retries,
                retry_rate=round(retries / cnt, 4) if cnt > 0 else 0.0,
                p50_latency_ms=p50_lat,
                p95_latency_ms=p95_lat,
                avg_latency_ms=avg_lat,
                policy_block_count=blocks,
                top_block_rule=top_block_rule,
            )
        )

    # 3. Prompt version breakdown
    prompt_dict: dict[str, list[Run]] = defaultdict(list)
    for r in runs:
        pv = r.prompt_version or "v1.0"
        prompt_dict[pv].append(r)

    prompt_breakdown: list[PromptVersionBreakdownItem] = []
    for pv, p_runs in sorted(prompt_dict.items()):
        cnt = len(p_runs)
        succ = sum(1 for r in p_runs if r.outcome == "success")
        known_c = [r.total_cost for r in p_runs if r.total_cost is not None]
        t_cost = round(sum(known_c), 6) if known_c else None
        cost_per_run = round(t_cost / cnt, 6) if (t_cost is not None and cnt > 0) else None
        cost_per_succ = round(t_cost / succ, 6) if (t_cost is not None and succ > 0) else None

        lats = [float(r.latency_ms) for r in p_runs if r.latency_ms is not None]
        p50_lat = round(calculate_percentile(lats, 50.0), 2)
        p95_lat = round(calculate_percentile(lats, 95.0), 2)
        avg_lat = round(statistics.mean(lats), 2) if lats else 0.0

        prompt_breakdown.append(
            PromptVersionBreakdownItem(
                prompt_version=pv,
                sample_size=cnt,
                completion_rate=round(succ / cnt, 4) if cnt > 0 else 0.0,
                total_cost=t_cost,
                cost_per_run=cost_per_run,
                cost_per_successful_task=cost_per_succ,
                p50_latency_ms=p50_lat,
                p95_latency_ms=p95_lat,
                avg_latency_ms=avg_lat,
            )
        )

    # 4. Time series daily breakdown
    daily_dict: dict[str, list[Run]] = defaultdict(list)
    run_day: dict[str, str] = {}
    for r in runs:
        d_str = r.started_at.strftime("%Y-%m-%d") if r.started_at else "unknown"
        daily_dict[d_str].append(r)
        run_day[r.id] = d_str

    tool_calls_by_day: dict[str, int] = defaultdict(int)
    for s in spans:
        if s.span_type == "tool":
            day = run_day.get(s.run_id)
            if day is not None:
                tool_calls_by_day[day] += 1

    time_series: list[TimeSeriesDataPoint] = []
    for d_str in sorted(daily_dict.keys()):
        d_runs = daily_dict[d_str]
        cnt = len(d_runs)
        succ = sum(1 for r in d_runs if r.outcome == "success")
        blocked = sum(1 for r in d_runs if r.outcome == "blocked")
        known_c = [r.total_cost for r in d_runs if r.total_cost is not None]
        t_cost = round(sum(known_c), 6) if known_c else None
        lats = [float(r.latency_ms) for r in d_runs if r.latency_ms is not None]
        avg_lat = round(statistics.mean(lats), 2) if lats else 0.0

        time_series.append(
            TimeSeriesDataPoint(
                date=d_str,
                sample_size=cnt,
                total_cost=t_cost,
                avg_latency_ms=avg_lat,
                success_rate=round(succ / cnt, 4) if cnt > 0 else 0.0,
                tool_calls=tool_calls_by_day.get(d_str, 0),
                blocked_runs=blocked,
            )
        )

    return {
        "models": model_breakdown,
        "tools": tool_breakdown,
        "prompt_versions": prompt_breakdown,
        "time_series": time_series,
    }


def compare_models(
    db: Session,
    model_a: str,
    model_b: str,
    task_id: Optional[str] = None,
    tag: Optional[str] = None,
    experiment_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    include_replays: bool = False,
) -> ModelComparisonResponse:
    query_a = db.query(Run).filter(Run.model == model_a)
    query_b = db.query(Run).filter(Run.model == model_b)

    if task_id:
        query_a = query_a.filter(Run.task_id == task_id)
        query_b = query_b.filter(Run.task_id == task_id)
    if start_date:
        query_a = query_a.filter(Run.started_at >= start_date)
        query_b = query_b.filter(Run.started_at >= start_date)
    if end_date:
        query_a = query_a.filter(Run.started_at <= end_date)
        query_b = query_b.filter(Run.started_at <= end_date)

    runs_a = _filter_runs_query(query_a.all(), tag=tag, experiment_id=experiment_id, include_replays=include_replays)
    runs_b = _filter_runs_query(query_b.all(), tag=tag, experiment_id=experiment_id, include_replays=include_replays)

    n_a = len(runs_a)
    n_b = len(runs_b)
    has_insufficient_data = (n_a < 20 or n_b < 20)

    def stats_for_runs(r_list: list[Run]) -> dict[str, Optional[float]]:
        cnt = len(r_list)
        if cnt == 0:
            return {
                "completion_rate": 0.0,
                "cost_per_run": None,
                "cost_per_successful_task": None,
                "p50_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "avg_tokens": 0.0,
                "avg_steps": 0.0,
            }
        succ = sum(1 for r in r_list if r.outcome == "success")
        known_c = [r.total_cost for r in r_list if r.total_cost is not None]
        t_cost = sum(known_c) if known_c else None
        
        c_per_run = round(t_cost / cnt, 6) if (t_cost is not None and cnt > 0) else None
        c_per_succ = round(t_cost / succ, 6) if (t_cost is not None and succ > 0) else None

        t_tok = sum(r.total_tokens for r in r_list if r.total_tokens is not None)
        t_steps = sum(r.step_count for r in r_list if r.step_count is not None)
        lats = [float(r.latency_ms) for r in r_list if r.latency_ms is not None]

        return {
            "completion_rate": round(succ / cnt, 4),
            "cost_per_run": c_per_run,
            "cost_per_successful_task": c_per_succ,
            "p50_latency_ms": round(calculate_percentile(lats, 50.0), 2),
            "p95_latency_ms": round(calculate_percentile(lats, 95.0), 2),
            "avg_tokens": round(t_tok / cnt, 1),
            "avg_steps": round(t_steps / cnt, 1),
        }

    stats_a = stats_for_runs(runs_a)
    stats_b = stats_for_runs(runs_b)

    metrics_def = [
        ("Task Completion Rate", "completion_rate", True), # True = higher is better
        ("Cost per Run ($)", "cost_per_run", False),       # False = lower is better
        ("Cost per Successful Task ($)", "cost_per_successful_task", False),
        ("p50 Latency (ms)", "p50_latency_ms", False),
        ("p95 Latency (ms)", "p95_latency_ms", False),
        ("Average Tokens", "avg_tokens", False),
        ("Average Steps", "avg_steps", False),
    ]

    metrics_res: list[ModelComparisonMetric] = []
    for label, key, higher_is_better in metrics_def:
        va = stats_a[key]
        vb = stats_b[key]

        diff_pct: Optional[float] = None
        winner: Optional[str] = None

        if va is None or vb is None:
            winner = "unknown"
        elif va == vb:
            winner = "insufficient_data" if has_insufficient_data else "tie"
            diff_pct = 0.0
        else:
            if va != 0:
                diff_pct = round(((vb - va) / abs(va)) * 100.0, 2)
            else:
                diff_pct = 100.0

            if has_insufficient_data:
                winner = "insufficient_data"
            elif higher_is_better:
                winner = "model_a" if va > vb else "model_b"
            else:
                winner = "model_a" if va < vb else "model_b"

        metrics_res.append(
            ModelComparisonMetric(
                metric_name=label,
                model_a_value=va,
                model_b_value=vb,
                diff_percentage=diff_pct,
                winner=winner,
            )
        )

    note = (
        "Comparisons are only valid when models are evaluated on the same task set "
        "with sufficient samples (n >= 20 per model). "
        "Status: 'insufficient_data' declared because sample size is below threshold."
        if has_insufficient_data
        else "Evaluated with statistical sample size (n >= 20 per side)."
    )

    return ModelComparisonResponse(
        model_a=model_a,
        model_b=model_b,
        model_a_sample_size=n_a,
        model_b_sample_size=n_b,
        metrics=metrics_res,
        note=note,
    )


def get_all_anomalies(
    db: Session,
    run_id: Optional[str] = None,
    task_id: Optional[str] = None,
    tag: Optional[str] = None,
    experiment_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    include_replays: bool = False,
) -> list[dict[str, Any]]:
    query = db.query(Run)
    if run_id:
        query = query.filter(Run.id == run_id)
    if task_id:
        query = query.filter(Run.task_id == task_id)
    if start_date:
        query = query.filter(Run.started_at >= start_date)
    if end_date:
        query = query.filter(Run.started_at <= end_date)

    raw_runs = query.all()
    runs = _filter_runs_query(raw_runs, tag=tag, experiment_id=experiment_id, include_replays=include_replays)
    if not runs:
        return []

    # 1. Statistical Outlier Anomalies computed per agent / task type
    # Baseline IQR is evaluated strictly within each agent or task type group (n >= 5)
    def extract_task_type_key(r: Run) -> str:
        tags = r.tags or {}
        key = tags.get("task_type") or tags.get("agent_label") or tags.get("agent")
        if not key and r.task_id:
            tid = str(r.task_id)
            # If task_id ends with a UUID-like suffix (e.g. task-name-1234abcd), strip it
            parts = tid.rsplit("-", 1)
            if len(parts) == 2 and len(parts[1]) in (8, 12, 32, 36):
                key = parts[0]
            else:
                key = tid
        return key or "default_agent_task"

    runs_by_task = defaultdict(list)
    for r in runs:
        t_key = extract_task_type_key(r)
        runs_by_task[t_key].append(r)

    outliers = []
    for t_key, task_runs in runs_by_task.items():
        if len(task_runs) >= 5:
            outliers.extend(detect_statistical_outliers(task_runs, min_sample_size=5, task_context=f"agent_task:{t_key}"))

    # 2. Repeated tool loop anomalies for each run (threshold consecutive >= 3)
    loop_anomalies = []
    run_ids = [r.id for r in runs]
    spans = db.query(Span).filter(Span.run_id.in_(run_ids)).all() if run_ids else []
    spans_by_run = defaultdict(list)
    for s in spans:
        spans_by_run[s.run_id].append(s)

    for r in runs:
        r_spans = spans_by_run[r.id]
        loops = detect_repeated_tool_loops(r_spans, r.id, threshold_consecutive=3)
        loop_anomalies.extend(loops)

    all_anomalies = loop_anomalies + outliers

    def _sort_key(a):
        dt = a.get("detected_at")
        if dt is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        if hasattr(dt, "tzinfo") and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    all_anomalies.sort(key=_sort_key, reverse=True)
    return all_anomalies
