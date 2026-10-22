from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from server.app.database import get_db
from server.app.schemas.analytics import (
    AnalyticsSummaryResponse,
    ModelBreakdownItem,
    ToolBreakdownItem,
    PromptVersionBreakdownItem,
    TimeSeriesDataPoint,
    ModelComparisonResponse,
    AnomalyItem,
)
from server.app.services.analytics_service import (
    get_analytics_summary,
    get_breakdown_metrics,
    compare_models,
    get_all_anomalies,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def read_analytics_summary(
    model: Optional[str] = Query(None, description="Filter by model"),
    prompt_version: Optional[str] = Query(None, description="Filter by prompt version"),
    task_id: Optional[str] = Query(None, description="Filter by task_id / agent type"),
    tag: Optional[str] = Query(None, description="Filter by tag (e.g. env:prod or tag key)"),
    experiment_id: Optional[str] = Query(None, description="Filter by experiment_id"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date ISO"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date ISO"),
    include_replays: bool = Query(False, description="Include replayed runs (excluded by default)"),
    db: Session = Depends(get_db),
):
    """Retrieve high-level summary KPIs (completion rate, latency p50/p95, total/avg cost, error rates, failure categories)."""
    return get_analytics_summary(
        db=db,
        model=model,
        prompt_version=prompt_version,
        task_id=task_id,
        tag=tag,
        experiment_id=experiment_id,
        start_date=start_date,
        end_date=end_date,
        include_replays=include_replays,
    )


@router.get("/breakdown")
def read_analytics_breakdown(
    task_id: Optional[str] = Query(None, description="Filter by task_id / agent type"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    experiment_id: Optional[str] = Query(None, description="Filter by experiment_id"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date ISO"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date ISO"),
    include_replays: bool = Query(False, description="Include replayed runs (excluded by default)"),
    db: Session = Depends(get_db),
):
    """Retrieve detailed aggregations broken down by model, tool name, prompt version, and daily time series."""
    return get_breakdown_metrics(
        db=db,
        task_id=task_id,
        tag=tag,
        experiment_id=experiment_id,
        start_date=start_date,
        end_date=end_date,
        include_replays=include_replays,
    )


@router.get("/anomalies", response_model=list[AnomalyItem])
def read_anomalies(
    run_id: Optional[str] = Query(None, description="Filter anomalies for a specific run"),
    task_id: Optional[str] = Query(None, description="Filter by task_id / agent type"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    experiment_id: Optional[str] = Query(None, description="Filter by experiment_id"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date ISO"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date ISO"),
    type: Optional[str] = Query(None, description="Filter by anomaly type: repeated_tool_loop, latency_outlier, step_count_outlier, cost_outlier"),
    severity: Optional[str] = Query(None, description="Filter by severity: low, medium, high, critical"),
    include_replays: bool = Query(False, description="Include replayed runs (excluded by default)"),
    db: Session = Depends(get_db),
):
    """Retrieve detected anomalies including repeated tool loops and statistical outliers (IQR)."""
    anomalies = get_all_anomalies(
        db=db,
        run_id=run_id,
        task_id=task_id,
        tag=tag,
        experiment_id=experiment_id,
        start_date=start_date,
        end_date=end_date,
        include_replays=include_replays,
    )
    if type:
        anomalies = [a for a in anomalies if a.get("type") == type]
    if severity:
        anomalies = [a for a in anomalies if a.get("severity") == severity]
    return anomalies


@router.get("/model-comparison", response_model=ModelComparisonResponse)
def read_model_comparison(
    model_a: str = Query(..., description="First model identifier"),
    model_b: str = Query(..., description="Second model identifier"),
    task_id: Optional[str] = Query(None, description="Filter by task_id / agent type for valid fair comparison"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    experiment_id: Optional[str] = Query(None, description="Filter by experiment_id"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date ISO"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date ISO"),
    include_replays: bool = Query(False, description="Include replayed runs (excluded by default)"),
    db: Session = Depends(get_db),
):
    """Compare performance, cost, latency, tokens, and step counts side-by-side between two models."""
    return compare_models(
        db=db,
        model_a=model_a,
        model_b=model_b,
        task_id=task_id,
        tag=tag,
        experiment_id=experiment_id,
        start_date=start_date,
        end_date=end_date,
        include_replays=include_replays,
    )
