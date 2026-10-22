import csv
import io
import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, cast, String
from server.app.database import get_db
from server.app.models.run import Run
from server.app.models.span import Span
from server.app.models.session import SessionModel
from server.app.models.api_key import ApiKey
from server.app.schemas.run import RunResponse, RunDetailResponse, RunListResponse, SpanResponse

router = APIRouter(prefix="/runs", tags=["runs"])


def _to_run_response(run: Run, db: Session) -> RunResponse:
    agent_label = None
    if run.api_key_id:
        key_record = db.query(ApiKey).filter(ApiKey.id == run.api_key_id).first()
        if key_record:
            agent_label = key_record.label

    ext_session_id = None
    if run.session_id:
        sess = db.query(SessionModel).filter(SessionModel.id == run.session_id).first()
        if sess:
            ext_session_id = sess.session_id

    return RunResponse(
        id=run.id,
        session_id=run.session_id,
        external_session_id=ext_session_id,
        api_key_id=run.api_key_id,
        agent_label=agent_label,
        task_id=run.task_id,
        prompt_version=run.prompt_version,
        model=run.model,
        outcome=run.outcome,
        failure_category=run.failure_category,
        total_cost=run.total_cost,
        total_tokens=run.total_tokens,
        prompt_tokens=run.prompt_tokens,
        completion_tokens=run.completion_tokens,
        latency_ms=run.latency_ms,
        step_count=run.step_count,
        error_message=run.error_message,
        tags=run.tags or {},
        started_at=run.started_at,
        ended_at=run.ended_at,
    )


@router.get("", response_model=RunListResponse)
def list_runs(
    outcome: Optional[str] = Query(None, description="Filter by outcome: success, failure, blocked, timed_out"),
    model: Optional[str] = Query(None, description="Filter by model name"),
    session_id: Optional[str] = Query(None, description="Filter by external or internal session_id"),
    search: Optional[str] = Query(None, description="Search keyword in prompts or tool arguments"),
    start_date: Optional[datetime] = Query(None, description="Filter runs after this timestamp"),
    end_date: Optional[datetime] = Query(None, description="Filter runs before this timestamp"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List runs with filtering, pagination, and full-text keyword search.
    """
    query = db.query(Run)

    if outcome:
        query = query.filter(Run.outcome == outcome)
    if model:
        query = query.filter(Run.model.ilike(f"%{model}%"))
    if session_id:
        # Match either internal session uuid or external session_id
        sess = db.query(SessionModel).filter(
            or_(SessionModel.id == session_id, SessionModel.session_id == session_id)
        ).first()
        if sess:
            query = query.filter(Run.session_id == sess.id)
        else:
            query = query.filter(Run.session_id == session_id)
    if start_date:
        query = query.filter(Run.started_at >= start_date)
    if end_date:
        query = query.filter(Run.started_at <= end_date)

    if search:
        search_pattern = f"%{search}%"
        # Search task_id or model on run, or search in spans (inputs/args)
        matching_span_run_ids = (
            db.query(Span.run_id)
            .filter(
                or_(
                    Span.name.ilike(search_pattern),
                    cast(Span.input_payload, String).ilike(search_pattern),
                    cast(Span.output_payload, String).ilike(search_pattern),
                )
            )
            .distinct()
            .scalar_subquery()
        )
        query = query.filter(
            or_(
                Run.task_id.ilike(search_pattern),
                Run.prompt_version.ilike(search_pattern),
                Run.id.in_(matching_span_run_ids),
            )
        )

    total = query.count()
    runs = query.order_by(desc(Run.started_at)).offset(offset).limit(limit).all()

    return RunListResponse(
        total=total,
        runs=[_to_run_response(r, db) for r in runs],
    )


@router.get("/export")
def export_runs(
    format: str = Query("json", pattern="^(json|csv)$"),

    outcome: Optional[str] = None,
    model: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Export runs as JSON or CSV.
    """
    query = db.query(Run)
    if outcome:
        query = query.filter(Run.outcome == outcome)
    if model:
        query = query.filter(Run.model.ilike(f"%{model}%"))

    runs = query.order_by(desc(Run.started_at)).all()

    if format == "json":
        export_data = []
        for r in runs:
            r_resp = _to_run_response(r, db)
            spans = (
                db.query(Span)
                .filter(Span.run_id == r.id)
                .order_by(Span.sequence_number.asc(), Span.started_at.asc())
                .all()
            )
            spans_resp = [SpanResponse.model_validate(s) for s in spans]
            run_dict = r_resp.model_dump(mode="json")
            run_dict["spans"] = [s.model_dump(mode="json") for s in spans_resp]
            export_data.append(run_dict)

        content = json.dumps(export_data, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=agentshield_runs.json"},
        )

    # CSV format
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id",
        "external_session_id",
        "agent_label",
        "task_id",
        "prompt_version",
        "model",
        "outcome",
        "failure_category",
        "total_cost",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "latency_ms",
        "step_count",
        "started_at",
        "ended_at",
    ])

    for r in runs:
        r_resp = _to_run_response(r, db)
        writer.writerow([
            r_resp.id,
            r_resp.external_session_id or "",
            r_resp.agent_label or "",
            r_resp.task_id or "",
            r_resp.prompt_version or "",
            r_resp.model or "",
            r_resp.outcome,
            r_resp.failure_category or "",
            r_resp.total_cost,
            r_resp.total_tokens,
            r_resp.prompt_tokens,
            r_resp.completion_tokens,
            r_resp.latency_ms,
            r_resp.step_count,
            r_resp.started_at.isoformat() if r_resp.started_at else "",
            r_resp.ended_at.isoformat() if r_resp.ended_at else "",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=agentshield_runs.csv"},
    )


@router.get("/{run_id}", response_model=RunDetailResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    """
    Get run details with full trace waterfall and spans.
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    base_resp = _to_run_response(run, db)
    spans = (
        db.query(Span)
        .filter(Span.run_id == run.id)
        .order_by(Span.sequence_number.asc(), Span.started_at.asc())
        .all()
    )
    spans_resp = [SpanResponse.model_validate(s) for s in spans]

    return RunDetailResponse(
        **base_resp.model_dump(),
        spans=spans_resp,
    )
