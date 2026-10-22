import os
from typing import Optional, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from server.app.database import get_db
from server.app.models.policy import PolicyVersion
from server.app.schemas.policy import (
    PolicyConfig,
    PolicyUploadRequest,
    PolicyVersionResponse,
    PolicyRollbackRequest,
)
from server.app.schemas.dry_run import DryRunRequest, DryRunResponse
from server.app.services.policy_engine import parse_policy_yaml
from server.app.services.dry_run import execute_dry_run
from server.app.services.auth import verify_admin_token

router = APIRouter(prefix="/policies", tags=["policies"])

DEFAULT_POLICY_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../../policies/default_policy.yaml")
)



def get_active_policy_record(db: Session) -> Optional[PolicyVersion]:
    """Retrieve active policy record, returning None if no policy is active."""
    return db.query(PolicyVersion).filter(PolicyVersion.is_active == True).first()


@router.get("")
def get_active_policy(db: Session = Depends(get_db)):
    """Retrieve the currently active policy configuration and metadata."""
    record = get_active_policy_record(db)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active policy found. Upload a policy using POST /policies.",
        )
    parsed = parse_policy_yaml(record.yaml_content)
    return {
        "id": record.id,
        "version_number": record.version_number,
        "yaml_content": record.yaml_content,
        "change_note": record.change_note,
        "parsed_policy": parsed.model_dump(),
        "created_at": record.created_at.isoformat(),
        "created_by": record.created_by,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def upload_policy(
    request: PolicyUploadRequest,
    admin_token: str = Depends(verify_admin_token),
    db: Session = Depends(get_db),
):
    """
    Upload and activate a new policy version.
    Requires X-Admin-Token.
    Rejects invalid YAML and preserves existing active policy on error.
    """
    # 1. Strictly validate YAML before database modifications
    try:
        parsed = parse_policy_yaml(request.yaml_content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Policy validation failed: {str(e)}",
        )

    # 2. Deactivate currently active version
    db.query(PolicyVersion).update({"is_active": False})

    # 3. Determine next version number
    max_version = db.query(PolicyVersion.version_number).order_by(desc(PolicyVersion.version_number)).first()
    next_ver = (max_version[0] + 1) if max_version else 1

    new_record = PolicyVersion(
        version_number=next_ver,
        yaml_content=request.yaml_content,
        change_note=request.change_note or f"Updated policy v{next_ver}",
        is_active=True,
        created_by="admin",
    )
    db.add(new_record)
    db.commit()
    db.refresh(new_record)

    return {
        "status": "success",
        "message": f"Policy v{next_ver} uploaded and activated successfully",
        "version_number": new_record.version_number,
        "policy_id": new_record.id,
    }


@router.get("/versions", response_model=list[PolicyVersionResponse])
def list_policy_versions(db: Session = Depends(get_db)):
    """List all historical policy versions and their active status."""
    records = db.query(PolicyVersion).order_by(desc(PolicyVersion.version_number)).all()
    return [
        PolicyVersionResponse(
            id=r.id,
            version_number=r.version_number,
            change_note=r.change_note,
            is_active=r.is_active,
            created_at=r.created_at.isoformat(),
            created_by=r.created_by,
        )
        for r in records
    ]


@router.post("/rollback")
def rollback_policy(
    request: PolicyRollbackRequest,
    admin_token: str = Depends(verify_admin_token),
    db: Session = Depends(get_db),
):
    """
    Rollback active policy to a previously saved version.
    Requires X-Admin-Token.
    """
    target = db.query(PolicyVersion).filter(PolicyVersion.version_number == request.target_version_number).first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy version {request.target_version_number} not found",
        )

    # Deactivate all and activate target
    db.query(PolicyVersion).update({"is_active": False})
    target.is_active = True
    db.commit()

    return {
        "status": "success",
        "message": f"Active policy successfully rolled back to v{target.version_number}",
        "active_version": target.version_number,
        "policy_id": target.id,
    }


@router.post("/dry-run", response_model=DryRunResponse)
def dry_run_policy(
    request: DryRunRequest,
    admin_token: str = Depends(verify_admin_token),
    db: Session = Depends(get_db),
):
    """
    Simulate impact of a candidate policy against recorded historical spans.
    Computes allow/deny/approval counts and returns exact diffs for each affected span.
    Requires X-Admin-Token.
    """
    yaml_content = request.candidate_yaml

    if not yaml_content and request.candidate_version_number is not None:
        rec = db.query(PolicyVersion).filter(PolicyVersion.version_number == request.candidate_version_number).first()
        if not rec:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate policy version {request.candidate_version_number} not found",
            )
        yaml_content = rec.yaml_content

    if not yaml_content or not yaml_content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either candidate_yaml or candidate_version_number must be provided",
        )

    try:
        candidate_config = parse_policy_yaml(yaml_content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Candidate policy validation failed: {str(e)}",
        )

    return execute_dry_run(
        db=db,
        candidate_policy=candidate_config,
        run_ids=request.run_ids,
        limit_runs=request.limit_runs,
    )


class PolicySimulateCallRequest(BaseModel):
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    candidate_yaml: Optional[str] = None


class PolicySimulateCallResponse(BaseModel):
    decision: str
    rule_id: Optional[str] = None
    reason: Optional[str] = None
    timeout_seconds: Optional[int] = None
    latency_ms: float


@router.post("/simulate-call", response_model=PolicySimulateCallResponse)
def simulate_policy_call(
    request: PolicySimulateCallRequest,
    admin_token: str = Depends(verify_admin_token),
    db: Session = Depends(get_db),
):
    """
    Pure side-effect-free evaluation of a single tool invocation against active (or candidate) policy.
    Zero database writes, zero rate-limit state writes, zero span logging.
    Requires X-Admin-Token.
    """
    import time
    from server.app.services.policy_engine import evaluate_policy

    t0 = time.perf_counter()
    if request.candidate_yaml:
        try:
            policy_config = parse_policy_yaml(request.candidate_yaml)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Candidate policy validation failed: {str(e)}",
            )
    else:
        active = get_active_policy_record(db)
        if not active:
            if os.path.exists(DEFAULT_POLICY_PATH):
                with open(DEFAULT_POLICY_PATH, "r", encoding="utf-8") as f:
                    policy_config = parse_policy_yaml(f.read())
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active policy found to simulate against",
                )
        else:
            policy_config = parse_policy_yaml(active.yaml_content)

    result = evaluate_policy(
        tool_name=request.tool_name,
        tool_args=request.tool_args,
        policy=policy_config,
        run_state=None,  # Pure check: zero budget side-effects, zero rate-limit state writes
    )
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)

    return PolicySimulateCallResponse(
        decision=result.decision,
        rule_id=result.rule_id,
        reason=result.reason,
        timeout_seconds=result.timeout_seconds,
        latency_ms=latency_ms,
    )

