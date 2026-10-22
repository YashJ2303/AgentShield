import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from server.app.database import get_db
from server.app.models.api_key import ApiKey
from server.app.models.approval import Approval
from server.app.models.run import Run
from server.app.schemas.gateway import (
    CheckToolRequest,
    CheckToolResponse,
    ScreenOutputRequest,
    ScreenOutputResponse,
)
from server.app.services.auth import verify_api_key
from server.app.services.policy_engine import evaluate_policy, parse_policy_yaml, RunState
from server.app.services.rate_limiter import get_rate_limit_counts_for_run, increment_rate_limit_counter
from server.app.services.redaction import redact_data
from server.app.services.approval_manager import compute_call_hash
from server.app.api.v1.policies import get_active_policy_record

router = APIRouter(prefix="/gateway", tags=["gateway"])


@router.post("/check", response_model=CheckToolResponse)
def check_tool_call(
    request: CheckToolRequest,
    api_key: ApiKey = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Synchronous pre-execution policy check before any tool call.
    Evaluates:
    - Budget limits (cost, tokens, steps, server-computed wall-clock time)
    - SQL safety checks via sqlglot
    - Path confinement and domain allowlists
    - Atomic DB rate limits
    - Approval creation if action is require_approval (stores redacted args and canonical call hash)
    """
    # 1. Fetch active policy version
    policy_record = get_active_policy_record(db)
    if not policy_record:
        return CheckToolResponse(
            decision="deny",
            rule_id="no_active_policy",
            reason="No active security policy configured; all tool calls are denied by default",
            policy_version_id=None,
        )

    policy_config = parse_policy_yaml(policy_record.yaml_content)

    # 2. Retrieve atomic tool counts from DB
    current_counts = get_rate_limit_counts_for_run(db, request.run_id)

    # 3. Compute elapsed wall-clock time server-side from run's started_at in DB
    now = datetime.now(timezone.utc)
    run_record = db.query(Run).filter(Run.id == request.run_id).first()
    if not run_record:
        run_record = Run(
            id=request.run_id,
            api_key_id=api_key.id if api_key else None,
            started_at=now,
            outcome="in_progress",
        )
        db.add(run_record)
        db.commit()
        db.refresh(run_record)

    run_started = run_record.started_at
    if run_started.tzinfo is None:
        run_started = run_started.replace(tzinfo=timezone.utc)
    server_elapsed_seconds = max(0.0, (now - run_started).total_seconds())

    # 4. Build run state with server-computed wall-clock time
    run_state = RunState(
        run_id=request.run_id,
        current_cost=request.current_running_cost,
        current_tokens=request.current_total_tokens,
        current_steps=request.current_step_count,
        elapsed_wall_time_seconds=server_elapsed_seconds,
        tool_call_counts=current_counts,
    )

    # 4. Pure function policy evaluation
    result = evaluate_policy(
        tool_name=request.tool_name,
        tool_args=request.tool_args,
        policy=policy_config,
        run_state=run_state,
    )

    # 5. Handle action
    if result.decision == "allow":
        # Atomically record execution count in DB
        increment_rate_limit_counter(db, request.run_id, request.tool_name)
        return CheckToolResponse(
            decision="allow",
            rule_id=result.rule_id,
            reason=result.reason,
            policy_version_id=policy_record.id,
        )

    elif result.decision == "require_approval":
        # 1. Compute canonical call hash binding approval strictly to (run_id, tool_name, args)
        call_hash = compute_call_hash(request.run_id, request.tool_name, request.tool_args)

        # 2. Redact tool_args with standard redaction engine BEFORE storing to prevent secret leakage
        redacted_args, _ = redact_data(request.tool_args)

        timeout_sec = result.timeout_seconds or 60
        approval = Approval(
            id=str(uuid.uuid4()),
            run_id=request.run_id,
            tool_name=request.tool_name,
            tool_args=redacted_args,
            call_hash=call_hash,
            status="pending",
            timeout_seconds=timeout_sec,
            requested_at=now,
            is_consumed=0,
        )
        db.add(approval)
        db.commit()
        db.refresh(approval)

        return CheckToolResponse(
            decision="pending",
            rule_id=result.rule_id,
            reason="Tool call requires human approval before proceeding",
            approval_id=approval.id,
            timeout_seconds=timeout_sec,
            call_hash=call_hash,
            policy_version_id=policy_record.id,
        )

    else:
        # Deny
        return CheckToolResponse(
            decision="deny",
            rule_id=result.rule_id,
            reason=result.reason or "Tool call denied by policy",
            policy_version_id=policy_record.id,
        )


@router.post("/screen-output", response_model=ScreenOutputResponse)
def screen_tool_output(
    request: ScreenOutputRequest,
    api_key: ApiKey = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Screens tool output for prompt injection attacks before returning it to the agent/model.
    - Evaluates heuristic detectors (instruction override, role spoofing, hidden text, base64 payloads)
    - Applies per-tool policy action (block | flag | sanitize) or active policy default
    - On block: replaces payload with safe refusal without quoting malicious text
    - On sanitize: removes malicious instruction while preserving benign output
    - Stores match metadata on the target span
    """
    from server.app.models.span import Span
    from server.app.services.injection_screener import default_screener
    from server.app.schemas.gateway import InjectionMatchItem

    # 1. Determine action from active policy
    policy_record = get_active_policy_record(db)
    action = "block" # safe default
    if policy_record:
        try:
            policy_config = parse_policy_yaml(policy_record.yaml_content)
            # Check default action
            if policy_config.injection_screening:
                action = policy_config.injection_screening.default_action
            # Check per-tool override
            for rule in policy_config.rules:
                if (rule.tool == request.tool_name or rule.tool == "*") and rule.injection_action:
                    action = rule.injection_action
                    break
        except Exception:
            action = "block"

    # 2. Execute screening pipeline
    screen_res = default_screener.screen(request.tool_output, action=action)

    # 3. Update database span record if span_id provided
    if request.span_id:
        target_span = db.query(Span).filter(Span.id == request.span_id).first()
        if target_span:
            target_span.injection_flag = screen_res.injection_flag
            target_span.injection_details = {
                "action": screen_res.action_taken,
                "matches": [
                    {
                        "category": m.category,
                        "pattern_name": m.pattern_name,
                        "detector": m.detector_name,
                        "start_offset": m.start_offset,
                        "end_offset": m.end_offset,
                        "confidence": m.confidence,
                        "details": m.details,
                    }
                    for m in screen_res.matches
                ],
                "reason": screen_res.reason,
            }
            if screen_res.action_taken == "block":
                target_span.policy_decision = "deny"
                target_span.policy_rule_id = "prompt_injection_detected"
                target_span.output_payload = {"error": screen_res.sanitized_output}
            elif screen_res.action_taken == "sanitize":
                target_span.output_payload = screen_res.sanitized_output
            try:
                db.commit()
            except Exception:
                db.rollback()

    match_items = [
        InjectionMatchItem(
            category=m.category,
            pattern_name=m.pattern_name,
            detector=m.detector_name,
            start_offset=m.start_offset,
            end_offset=m.end_offset,
            confidence=m.confidence,
            details=m.details,
        )
        for m in screen_res.matches
    ]

    return ScreenOutputResponse(
        action_taken=screen_res.action_taken,
        is_safe=screen_res.is_safe,
        injection_flag=screen_res.injection_flag,
        sanitized_output=screen_res.sanitized_output,
        matches=match_items,
        reason=screen_res.reason,
    )
