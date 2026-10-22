import json
from typing import Any, Optional
from datetime import datetime, timezone
import statistics

from server.app.services.approval_manager import _normalize_numbers


def calculate_percentile(data: list[float], percentile: float) -> float:
    """
    Calculate the p-th percentile (0 <= percentile <= 100) using linear interpolation.
    Handles empty arrays (0.0) and single-element arrays (returns element).
    """
    if not data:
        return 0.0
    if len(data) == 1:
        return float(data[0])

    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (percentile / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return float(sorted_data[-1])
    d = k - f
    return float(sorted_data[f] + d * (sorted_data[c] - sorted_data[f]))


def detect_repeated_tool_loops(
    spans: list[Any],
    run_id: str,
    threshold_consecutive: int = 3,
) -> list[dict[str, Any]]:
    """
    Detect repeated tool loops in a run's spans.
    Exact canonical definition: The same tool invoked with the same canonical
    arguments N or more times consecutively (where N = threshold_consecutive >= 3).
    """
    anomalies: list[dict[str, Any]] = []

    tool_spans = [s for s in spans if getattr(s, "span_type", None) == "tool"]
    if not tool_spans:
        return anomalies

    # Sort strictly by execution sequence number
    tool_spans.sort(key=lambda s: (getattr(s, "sequence_number", 0), getattr(s, "started_at", datetime.min)))

    # Canonicalize each tool call to (tool_name, canonical_json_args)
    calls: list[tuple[str, str]] = []
    for s in tool_spans:
        t_name = getattr(s, "name", "unknown")
        raw_input = getattr(s, "input_payload", {}) or {}
        # Ensure number canonicalization (e.g. 250000 vs 250000.0) is stable
        norm_input = _normalize_numbers(raw_input)
        try:
            canon_json = json.dumps(norm_input, sort_keys=True, separators=(",", ":"))
        except Exception:
            canon_json = str(norm_input)
        calls.append((t_name, canon_json))

    n = len(calls)
    if n < threshold_consecutive:
        return anomalies

    current_streak = 1
    for i in range(1, n):
        if calls[i] == calls[i - 1]:
            current_streak += 1
            if i == n - 1 and current_streak >= threshold_consecutive:
                tool_name = calls[i][0]
                anomalies.append({
                    "id": f"loop-consec-{run_id}-{i}",
                    "run_id": run_id,
                    "type": "repeated_tool_loop",
                    "severity": "critical" if current_streak >= 5 else "high",
                    "metric": "consecutive_calls",
                    "value": current_streak,
                    "sample_size": n,
                    "baseline_reference": f"Max allowable identical consecutive calls is {threshold_consecutive - 1}",
                    "message": f"Repeated tool loop detected: tool '{tool_name}' invoked {current_streak} times consecutively with identical arguments.",
                    "detected_at": datetime.now(timezone.utc),
                })
        else:
            if current_streak >= threshold_consecutive:
                tool_name = calls[i - 1][0]
                anomalies.append({
                    "id": f"loop-consec-{run_id}-{i-1}",
                    "run_id": run_id,
                    "type": "repeated_tool_loop",
                    "severity": "critical" if current_streak >= 5 else "high",
                    "metric": "consecutive_calls",
                    "value": current_streak,
                    "sample_size": n,
                    "baseline_reference": f"Max allowable identical consecutive calls is {threshold_consecutive - 1}",
                    "message": f"Repeated tool loop detected: tool '{tool_name}' invoked {current_streak} times consecutively with identical arguments.",
                    "detected_at": datetime.now(timezone.utc),
                })
            current_streak = 1

    return anomalies


def detect_statistical_outliers(
    runs: list[Any],
    min_sample_size: int = 5,
    task_context: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Detect statistical outliers across runs using the Interquartile Range (IQR) method.
    Metrics evaluated: latency_ms, step_count, total_cost.
    Requires minimum sample size (min_sample_size >= 5) to prevent noise on tiny samples.
    Outlier threshold = Q3 + 1.5 * IQR.
    Extreme threshold = Q3 + 3.0 * IQR.
    """
    anomalies: list[dict[str, Any]] = []
    sample_size = len(runs)
    if sample_size < min_sample_size:
        return anomalies

    metrics = [
        ("latency_ms", "latency_outlier", "Latency (ms)", 500.0),
        ("step_count", "step_count_outlier", "Step Count", 5.0),
        ("total_cost", "cost_outlier", "Total Cost ($)", 0.05),
    ]

    for field, outlier_type, label, min_floor in metrics:
        # Extract valid numeric values
        raw_values = [getattr(r, field, None) for r in runs]
        valid_values = [float(v) for v in raw_values if v is not None]
        if len(valid_values) < min_sample_size:
            continue

        sorted_vals = sorted(valid_values)
        q1 = calculate_percentile(sorted_vals, 25.0)
        q3 = calculate_percentile(sorted_vals, 75.0)
        iqr = q3 - q1

        if iqr <= 0:
            if len(set(sorted_vals)) > 1:
                mean_val = statistics.mean(sorted_vals)
                std_val = statistics.stdev(sorted_vals)
                threshold = max(mean_val + 2.0 * std_val, min_floor)
                extreme_thresh = max(mean_val + 3.0 * std_val, min_floor)
            else:
                continue
        else:
            threshold = max(q3 + 1.5 * iqr, min_floor)
            extreme_thresh = max(q3 + 3.0 * iqr, min_floor)

        for r in runs:
            val = getattr(r, field, None)
            if val is not None and float(val) > threshold:
                f_val = float(val)
                severity = "critical" if f_val >= extreme_thresh else "high"
                
                # Normalize timestamp safely
                r_dt = getattr(r, "started_at", None)
                if r_dt is None:
                    detected_dt = datetime.now(timezone.utc)
                elif r_dt.tzinfo is None:
                    detected_dt = r_dt.replace(tzinfo=timezone.utc)
                else:
                    detected_dt = r_dt

                context_suffix = f" for task '{task_context}'" if task_context else ""
                anomalies.append({
                    "id": f"outlier-{outlier_type}-{r.id}",
                    "run_id": r.id,
                    "type": outlier_type,
                    "severity": severity,
                    "metric": field,
                    "value": round(f_val, 4) if field == "total_cost" else int(f_val),
                    "sample_size": sample_size,
                    "baseline_reference": f"Q3={round(q3, 2)}, IQR={round(iqr, 2)}, Threshold={round(threshold, 2)}{context_suffix}",
                    "message": f"Run {r.id[:8]} exhibited statistical outlier in {label}{context_suffix}: {f_val} exceeds upper bound {threshold:.2f} (n={sample_size}).",
                    "detected_at": detected_dt,
                })

    return anomalies
