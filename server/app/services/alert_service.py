import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc

from server.app.models.alert import AlertRule, AlertEvent
from server.app.models.run import Run
from server.app.models.span import Span
from server.app.services.anomaly_detector import detect_repeated_tool_loops

logger = logging.getLogger("agentshield.alerts")


def dispatch_webhook(webhook_url: str, payload: dict[str, Any], timeout_seconds: float = 2.0) -> bool:
    """Safely dispatch an alert event payload to a webhook URL."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "AgentShield-AlertDispatcher/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        logger.warning(f"Failed to dispatch alert webhook to {webhook_url}: {e}")
        return False


def evaluate_rules(db: Session, trigger_run_id: Optional[str] = None) -> list[AlertEvent]:
    """Evaluate all active alert rules against recent run windows."""
    active_rules: list[AlertRule] = db.query(AlertRule).filter(AlertRule.is_active == True).all()
    if not active_rules:
        return []

    new_events: list[AlertEvent] = []

    for rule in active_rules:
        window_size = max(1, rule.window_runs)
        recent_runs: list[Run] = (
            db.query(Run)
            .order_by(desc(Run.started_at))
            .limit(window_size)
            .all()
        )
        if not recent_runs:
            continue

        run_count = len(recent_runs)
        metric_value: float = 0.0

        if rule.metric == "failure_rate":
            failed = sum(1 for r in recent_runs if r.outcome != "success")
            metric_value = round(failed / run_count, 4)

        elif rule.metric in ("cost", "avg_cost"):
            total_c = sum(r.total_cost for r in recent_runs)
            metric_value = round(total_c / run_count, 6)

        elif rule.metric == "tool_error_rate":
            r_ids = [r.id for r in recent_runs]
            t_spans = db.query(Span).filter(Span.run_id.in_(r_ids), Span.span_type == "tool").all()
            if t_spans:
                errs = sum(1 for s in t_spans if s.error)
                metric_value = round(errs / len(t_spans), 4)
            else:
                metric_value = 0.0

        elif rule.metric in ("latency_ms", "avg_latency"):
            lats = [r.latency_ms for r in recent_runs if r.latency_ms is not None]
            metric_value = round(sum(lats) / len(lats), 2) if lats else 0.0

        elif rule.metric == "loop_count":
            loop_cnt = 0
            for r in recent_runs:
                loops = detect_repeated_tool_loops(r.spans, r.id)
                loop_cnt += len(loops)
            metric_value = float(loop_cnt)

        else:
            logger.warning(f"Unknown alert metric: {rule.metric}")
            continue

        # Evaluate condition
        is_triggered = False
        thresh = rule.threshold
        cond = rule.condition.lower()
        if cond == "gt" and metric_value > thresh:
            is_triggered = True
        elif cond in ("gte", "ge") and metric_value >= thresh:
            is_triggered = True
        elif cond == "lt" and metric_value < thresh:
            is_triggered = True
        elif cond in ("lte", "le") and metric_value <= thresh:
            is_triggered = True
        elif cond == "eq" and metric_value == thresh:
            is_triggered = True

        if is_triggered:
            msg = (
                f"Alert rule '{rule.name}' triggered: metric '{rule.metric}' value {metric_value} "
                f"{rule.condition} threshold {thresh} over the last {run_count} runs."
            )
            event = AlertEvent(
                rule_id=rule.id,
                run_id=trigger_run_id or (recent_runs[0].id if recent_runs else None),
                message=msg,
                details={
                    "metric": rule.metric,
                    "condition": rule.condition,
                    "threshold": thresh,
                    "actual_value": metric_value,
                    "window_size": run_count,
                },
                created_at=datetime.now(timezone.utc),
            )
            db.add(event)
            rule.last_triggered_at = datetime.now(timezone.utc)
            new_events.append(event)

            if rule.webhook_url:
                payload = {
                    "event_id": event.id,
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "message": msg,
                    "metric": rule.metric,
                    "value": metric_value,
                    "threshold": thresh,
                    "timestamp": event.created_at.isoformat(),
                }
                dispatch_webhook(rule.webhook_url, payload)

    if new_events:
        db.commit()

    return new_events
