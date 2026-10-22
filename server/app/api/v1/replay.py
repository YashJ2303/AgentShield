from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, Any
from datetime import datetime, timezone

from server.app.database import get_db
from server.app.models.run import Run
from server.app.models.span import Span
from server.app.models.replay import Replay
from server.app.models.policy import PolicyVersion
from server.app.schemas.replay import (
    ReplayRequest,
    ReplayResponse,
    ReplaySampleResponse,
    TrajectoryStepDiffResponse,
    SensitivityPoint,
    BatchReplayRequest,
    BatchReplayResponse,
)
from server.app.services.replay_engine import (
    IncidentReplayHarness,
    ScriptedMockAgent,
)
from server.app.services.auth import verify_admin_token, verify_api_key

router = APIRouter(prefix="/replay", tags=["replay"])


@router.post("", response_model=ReplayResponse)
def execute_incident_replay(
    request: ReplayRequest,
    db: Session = Depends(get_db),
    _admin: str = Depends(verify_admin_token),
):
    """
    Executes incident replay of a recorded trace against a candidate model, altered prompt,
    or candidate security policy.
    - Uses frozen tool outputs from original recorded spans
    - Guarantees zero live tool calls (cache-miss returns recorded synthetic response)
    - Re-evaluates candidate policy using pure evaluate_policy()
    - Computes fidelity score (0.4 S_tool + 0.3 S_args + 0.3 S_outcome)
    - Measures multi-sample spread (N=3) and flags regressions
    """
    orig_run: Optional[Run] = db.query(Run).filter(Run.id == request.original_run_id).first()
    if not orig_run:
        raise HTTPException(status_code=404, detail=f"Recorded run '{request.original_run_id}' not found")

    orig_spans: list[Span] = (
        db.query(Span)
        .filter(Span.run_id == request.original_run_id, Span.span_type == "tool")
        .order_by(Span.sequence_number.asc(), Span.started_at.asc())
        .all()
    )

    planned_calls = [(s.name, s.input_payload if isinstance(s.input_payload, dict) else {}) for s in orig_spans]

    # Resolve candidate policy YAML if ID passed
    candidate_yaml = request.candidate_policy_yaml
    if not candidate_yaml and request.candidate_policy_version_id:
        pol_rec = db.query(PolicyVersion).filter(PolicyVersion.id == request.candidate_policy_version_id).first()
        if pol_rec:
            candidate_yaml = pol_rec.yaml_content

    # If target prompt or model indicates an intentional behavioral shift, adjust mock agent accordingly
    behavior_shift = None
    if request.target_model and "shift" in request.target_model.lower():
        behavior_shift = "altered_args"
    elif request.target_prompt and "forbidden" in request.target_prompt.lower():
        behavior_shift = "forbidden_tool"

    agent = ScriptedMockAgent(
        planned_calls=planned_calls,
        final_outcome=orig_run.outcome,
        behavior_shift=behavior_shift,
    )

    harness = IncidentReplayHarness(db)
    try:
        res = harness.replay_run(
            original_run_id=request.original_run_id,
            agent=agent,
            target_model=request.target_model,
            target_prompt=request.target_prompt,
            candidate_policy_yaml=candidate_yaml,
            candidate_policy_version_id=request.candidate_policy_version_id,
            matching_threshold=request.matching_threshold,
            num_samples=request.num_samples,
            compute_sensitivity=request.compute_sensitivity,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Replay execution failed: {str(e)}")

    sample_res = [
        ReplaySampleResponse(
            sample_index=s.sample_index,
            fidelity_score=s.fidelity_score,
            s_tool=s.s_tool,
            s_args=s.s_args,
            s_outcome=s.s_outcome,
            cache_miss_rate=s.cache_miss_rate,
            replayed_outcome=s.replayed_outcome,
            replayed_tools=s.replayed_tools,
        )
        for s in res.sample_results
    ]

    diff_res = [
        TrajectoryStepDiffResponse(
            step_number=d["step_number"],
            tool_name_recorded=d["tool_name_recorded"],
            tool_name_replayed=d["tool_name_replayed"],
            tool_match=d["tool_match"],
            args_recorded=d["args_recorded"],
            args_replayed=d["args_replayed"],
            arg_similarity=d["arg_similarity"],
            output_recorded=d["output_recorded"],
            output_replayed=d["output_replayed"],
            policy_decision_recorded=d["policy_decision_recorded"],
            policy_decision_replayed=d["policy_decision_replayed"],
            is_cache_miss=d["is_cache_miss"],
        )
        for d in res.trajectory_diff
    ]

    sens_res = None
    if res.sensitivity_table:
        sens_res = [
            SensitivityPoint(
                threshold=pt["threshold"],
                fidelity_score=pt["fidelity_score"],
                cache_miss_rate=pt["cache_miss_rate"],
                cache_misses=pt["cache_misses"],
                total_calls=pt["total_calls"],
            )
            for pt in res.sensitivity_table
        ]

    return ReplayResponse(
        replay_id=res.replay_id,
        original_run_id=res.original_run_id,
        target_model=res.target_model,
        target_prompt_version=res.target_prompt_version,
        candidate_policy_version_id=res.candidate_policy_version_id,
        outcome=res.sample_results[0].replayed_outcome if res.sample_results else "success",
        fidelity_score=res.mean_fidelity,
        fidelity_truncated=res.mean_truncated_fidelity,
        cache_miss_rate=res.mean_cache_miss_rate,
        fidelity_spread=res.fidelity_spread,
        fidelity_range=res.fidelity_range,
        fidelity_std_dev=res.fidelity_std_dev,
        regression_detected=res.regression_detected,
        regression_reasons=res.regression_reasons,
        sample_results=sample_res,
        trajectory_diff=diff_res,
        sensitivity_table=sens_res,
        created_at=datetime.now(timezone.utc),
    )


@router.get("/{replay_id}", response_model=ReplayResponse)
def read_replay_record(
    replay_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve historical replay execution result and trajectory diff."""
    rec: Optional[Replay] = db.query(Replay).filter(Replay.id == replay_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"Replay '{replay_id}' not found")

    sample_items = [
        ReplaySampleResponse(
            sample_index=s.get("sample_index", 1),
            fidelity_score=s.get("fidelity_score", 0.0),
            s_tool=s.get("s_tool", 0.0),
            s_args=s.get("s_args", 0.0),
            s_outcome=s.get("s_outcome", 0.0),
            cache_miss_rate=s.get("cache_miss_rate", 0.0),
            replayed_outcome=s.get("replayed_outcome", "success"),
            replayed_tools=s.get("replayed_tools", []),
        )
        for s in (rec.sample_results or [])
    ]

    steps = (rec.trajectory_diff or {}).get("steps", [])
    diff_items = [
        TrajectoryStepDiffResponse(
            step_number=d.get("step_number", idx + 1),
            tool_name_recorded=d.get("tool_name_recorded"),
            tool_name_replayed=d.get("tool_name_replayed"),
            tool_match=d.get("tool_match", False),
            args_recorded=d.get("args_recorded"),
            args_replayed=d.get("args_replayed"),
            arg_similarity=d.get("arg_similarity", 0.0),
            output_recorded=d.get("output_recorded"),
            output_replayed=d.get("output_replayed"),
            policy_decision_recorded=d.get("policy_decision_recorded"),
            policy_decision_replayed=d.get("policy_decision_replayed"),
            is_cache_miss=d.get("is_cache_miss", False),
        )
        for idx, d in enumerate(steps)
    ]

    reasons = (rec.trajectory_diff or {}).get("regression_reasons", [])

    return ReplayResponse(
        replay_id=rec.id,
        original_run_id=rec.original_run_id,
        target_model=rec.target_model,
        target_prompt_version=rec.target_prompt_version,
        candidate_policy_version_id=rec.candidate_policy_version_id,
        outcome=rec.outcome,
        fidelity_score=rec.fidelity_score,
        cache_miss_rate=rec.cache_miss_rate,
        fidelity_spread=0.0,
        regression_detected=len(reasons) > 0,
        regression_reasons=reasons,
        sample_results=sample_items,
        trajectory_diff=diff_items,
        sensitivity_table=None,
        created_at=rec.created_at,
    )


@router.get("", response_model=list[dict[str, Any]])
def list_replays(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    original_run_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List historical incident replay records."""
    query = db.query(Replay)
    if original_run_id:
        query = query.filter(Replay.original_run_id == original_run_id)
    replays = query.order_by(Replay.created_at.desc()).offset(offset).limit(limit).all()

    return [
        {
            "id": r.id,
            "original_run_id": r.original_run_id,
            "target_model": r.target_model,
            "target_prompt_version": r.target_prompt_version,
            "fidelity_score": r.fidelity_score,
            "cache_miss_rate": r.cache_miss_rate,
            "outcome": r.outcome,
        }
        for r in replays
    ]


@router.post("/batch", response_model=BatchReplayResponse)
def execute_batch_replay(
    request: BatchReplayRequest,
    db: Session = Depends(get_db),
    _admin: str = Depends(verify_admin_token),
):
    """
    Executes batch incident replay across multiple recorded run IDs.
    - Zero live tool calls (all outputs from recorded traces or synthetic responses)
    - Aggregates mean fidelity, truncated fidelity, cache miss rates, and regression flags
    - Exports Markdown and JSON aggregate reports
    - Replays remain tagged and excluded from analytics
    """
    harness = IncidentReplayHarness(db)
    return harness.replay_batch(
        run_ids=request.run_ids,
        target_model=request.target_model,
        target_prompt=request.target_prompt,
        candidate_policy_yaml=request.candidate_policy_yaml,
        matching_threshold=request.matching_threshold,
        num_samples=request.num_samples,
        compute_sensitivity=request.compute_sensitivity,
    )


replays_router = APIRouter(prefix="/replays", tags=["replay"])


@replays_router.get("", response_model=list[dict[str, Any]])
def list_replays_plural(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    original_run_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _auth: Any = Depends(verify_api_key),
):
    return list_replays(limit=limit, offset=offset, original_run_id=original_run_id, db=db)


@replays_router.post("/batch", response_model=BatchReplayResponse)
def execute_batch_replay_plural(
    request: BatchReplayRequest,
    db: Session = Depends(get_db),
    _admin: str = Depends(verify_admin_token),
):
    return execute_batch_replay(request=request, db=db, _admin=_admin)
