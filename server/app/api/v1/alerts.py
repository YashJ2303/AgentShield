from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional

from server.app.database import get_db
from server.app.models.alert import AlertRule, AlertEvent
from server.app.schemas.alert import AlertRuleCreate, AlertRuleResponse, AlertEventResponse
from server.app.services.alert_service import evaluate_rules
from server.app.api.v1.approvals import verify_admin_token

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/rules", response_model=list[AlertRuleResponse])
def list_alert_rules(db: Session = Depends(get_db)):
    """List all configured alert rules."""
    return db.query(AlertRule).order_by(desc(AlertRule.created_at)).all()


@router.post("/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
def create_alert_rule(
    rule_in: AlertRuleCreate,
    db: Session = Depends(get_db),
    admin_token: str = Depends(verify_admin_token),
):
    """Create a new alert rule. Requires X-Admin-Token header."""
    valid_metrics = {"failure_rate", "cost", "avg_cost", "tool_error_rate", "latency_ms", "avg_latency", "loop_count"}
    if rule_in.metric not in valid_metrics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid metric '{rule_in.metric}'. Valid choices: {sorted(list(valid_metrics))}",
        )
    valid_conditions = {"gt", "gte", "lt", "lte", "eq"}
    if rule_in.condition.lower() not in valid_conditions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid condition '{rule_in.condition}'. Valid choices: {sorted(list(valid_conditions))}",
        )

    rule = AlertRule(
        name=rule_in.name,
        metric=rule_in.metric,
        condition=rule_in.condition.lower(),
        threshold=rule_in.threshold,
        window_runs=rule_in.window_runs,
        webhook_url=rule_in.webhook_url,
        is_active=rule_in.is_active,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}")
def delete_alert_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    admin_token: str = Depends(verify_admin_token),
):
    """Delete an alert rule. Requires X-Admin-Token header."""
    rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found.")
    db.delete(rule)
    db.commit()
    return {"status": "deleted", "rule_id": rule_id}


@router.post("/evaluate", response_model=list[AlertEventResponse])
def trigger_alert_evaluation(
    run_id: Optional[str] = Query(None, description="Optional run ID triggering the evaluation"),
    db: Session = Depends(get_db),
):
    """Evaluate active alert rules against recent runs and dispatch webhooks for triggered rules."""
    new_events = evaluate_rules(db=db, trigger_run_id=run_id)
    return new_events


@router.get("/events", response_model=list[AlertEventResponse])
def list_alert_events(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List recent alert events."""
    return db.query(AlertEvent).order_by(desc(AlertEvent.created_at)).limit(limit).all()
