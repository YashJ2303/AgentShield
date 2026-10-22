from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from server.app.database import get_db
from server.app.models.api_key import ApiKey
from server.app.models.session import SessionModel
from server.app.models.run import Run
from server.app.models.span import Span
from server.app.schemas.ingest import BatchIngestRequest, BatchIngestResponse
from server.app.services.auth import verify_api_key
from server.app.services.redaction import redact_data
from server.app.services.pricing import calculate_cost

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/spans", response_model=BatchIngestResponse)
def ingest_spans(
    request: BatchIngestRequest,
    api_key: ApiKey = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Batch ingest spans from the SDK.
    Enforces sensitive data redaction, links runs and sessions,
    and recalculates token counts, costs, and step totals.
    """
    if not request.spans:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No spans provided in ingest payload",
        )

    # All spans in a batch belong to a common run_id
    run_id = request.spans[0].run_id

    # 1. Resolve or create Session if session_id provided
    session_db_id = None
    if request.session_id:
        sess = db.query(SessionModel).filter(SessionModel.session_id == request.session_id).first()
        if not sess:
            sess = SessionModel(
                session_id=request.session_id,
                name=f"Session {request.session_id}",
            )
            db.add(sess)
            db.flush()
        session_db_id = sess.id

    # 2. Resolve or create Run
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        earliest_start = min(s.started_at for s in request.spans)
        run = Run(
            id=run_id,
            session_id=session_db_id,
            api_key_id=api_key.id,
            task_id=request.task_id,
            prompt_version=request.prompt_version,
            model=request.model,
            outcome=request.outcome.value if request.outcome else "success",
            tags=request.tags or {},
            started_at=earliest_start,
        )
        db.add(run)
        db.flush()
    else:
        # Update metadata if newly provided
        if session_db_id and not run.session_id:
            run.session_id = session_db_id
        if request.task_id and not run.task_id:
            run.task_id = request.task_id
        if request.prompt_version and not run.prompt_version:
            run.prompt_version = request.prompt_version
        if request.model and not run.model:
            run.model = request.model
        if request.outcome:
            run.outcome = request.outcome.value
        if request.tags:
            run.tags = {**(run.tags or {}), **request.tags}

    # 3. Process each span with server-side redaction verification
    total_batch_redactions = 0
    for idx, span_item in enumerate(request.spans, start=1):
        # Redact input payload
        redacted_input, in_count = redact_data(span_item.input_payload)
        # Redact output payload
        redacted_output, out_count = redact_data(span_item.output_payload)

        span_redaction_count = (span_item.redaction_count or 0) + in_count + out_count
        total_batch_redactions += span_redaction_count

        assigned_seq = span_item.sequence_number if (span_item.sequence_number and span_item.sequence_number > 0) else idx
        span_obj = db.query(Span).filter(Span.id == span_item.id).first() if span_item.id else None
        if not span_obj:
            span_obj = Span(
                id=span_item.id,
                run_id=run.id,
                sequence_number=assigned_seq,
                parent_span_id=span_item.parent_span_id,
                policy_version_id=span_item.policy_version_id,
                span_type=span_item.span_type.value,

                name=span_item.name,
                input_payload=redacted_input,
                output_payload=redacted_output,
                latency_ms=span_item.latency_ms or 0,
                token_counts=span_item.token_counts or {},
                error=span_item.error,
                redaction_count=span_redaction_count,
                policy_decision=span_item.policy_decision,
                policy_rule_id=span_item.policy_rule_id,
                injection_flag=bool(span_item.injection_flag),
                injection_details=span_item.injection_details,
                started_at=span_item.started_at,
                ended_at=span_item.ended_at,
            )
            db.add(span_obj)
        else:
            span_obj.output_payload = redacted_output
            span_obj.ended_at = span_item.ended_at
            span_obj.latency_ms = span_item.latency_ms or span_obj.latency_ms
            span_obj.token_counts = span_item.token_counts or span_obj.token_counts
            span_obj.error = span_item.error or span_obj.error
            span_obj.redaction_count = span_redaction_count
            span_obj.policy_decision = span_item.policy_decision or span_obj.policy_decision

        # Update run outcome based on span verdicts
        if span_item.policy_decision == "deny" and run.outcome == "success":
            run.outcome = "blocked"
            run.failure_category = "policy_block"
        elif span_item.error and run.outcome == "success":
            run.outcome = "failure"
            run.failure_category = "tool_error" if span_item.span_type.value == "tool" else "other"

    db.flush()

    # 4. Recalculate run aggregates
    all_spans = db.query(Span).filter(Span.run_id == run.id).all()
    step_count = sum(1 for s in all_spans if s.span_type == "tool")
    p_tokens = sum(s.token_counts.get("prompt_tokens", 0) for s in all_spans if s.token_counts)
    c_tokens = sum(s.token_counts.get("completion_tokens", 0) for s in all_spans if s.token_counts)
    tot_tokens = p_tokens + c_tokens

    def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

    # Latency: difference between run started_at and latest ended_at
    all_end_times = [_ensure_utc(s.ended_at) for s in all_spans if s.ended_at]
    run_started_utc = _ensure_utc(run.started_at)
    latest_ended = max(all_end_times + [run_started_utc])
    duration_ms = int((latest_ended - run_started_utc).total_seconds() * 1000)

    run.step_count = step_count
    run.prompt_tokens = p_tokens
    run.completion_tokens = c_tokens
    run.total_tokens = tot_tokens
    run.latency_ms = max(duration_ms, 0)
    run.ended_at = latest_ended
    run.total_cost = calculate_cost(run.model, p_tokens, c_tokens)


    db.commit()

    return BatchIngestResponse(
        status="ok",
        run_id=run.id,
        spans_ingested=len(request.spans),
        redaction_count=total_batch_redactions,
        outcome=run.outcome,
    )
