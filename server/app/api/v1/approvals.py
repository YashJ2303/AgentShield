from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import update, desc

from server.app.database import get_db
from server.app.config import settings
from server.app.models.approval import Approval
from server.app.schemas.approval import (
    ApprovalResponse,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalConsumeRequest,
    ApprovalConsumeResponse,
)
from server.app.services.approval_manager import (
    compute_call_hash,
    expire_if_timed_out,
    batch_expire_pending_approvals,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])


def verify_admin_token(x_admin_token: Optional[str] = Header(None)) -> str:
    """
    Enforces shared secret admin authentication for approval decisions.
    Note: 'decided_by' is self-reported and unauthenticated; the identity
    guarantee is solely anchored by possession of this valid X-Admin-Token.
    """
    if not settings.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_TOKEN is not configured on this server.",
        )
    if not x_admin_token or x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-Admin-Token header.",
        )
    return x_admin_token


def _build_approval_response(approval: Approval, now: datetime) -> ApprovalResponse:
    req_at = approval.requested_at
    if req_at.tzinfo is None:
        req_at = req_at.replace(tzinfo=timezone.utc)
    
    elapsed = (now - req_at).total_seconds()
    remaining = max(0.0, float(approval.timeout_seconds) - elapsed)
    if approval.status != "pending":
        remaining = 0.0

    return ApprovalResponse(
        id=approval.id,
        run_id=approval.run_id,
        span_id=approval.span_id,
        tool_name=approval.tool_name,
        tool_args=approval.tool_args or {},
        call_hash=approval.call_hash,
        status=approval.status,
        timeout_seconds=approval.timeout_seconds,
        remaining_seconds=round(remaining, 1),
        requested_at=req_at,
        decided_at=approval.decided_at,
        decision_reason=approval.decision_reason,
        decided_by=approval.decided_by,
        is_consumed=bool(approval.is_consumed),
    )


@router.get("", response_model=list[ApprovalResponse])
def list_approvals(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Lists approval requests with read-time timeout expiry.
    Read endpoint is unauthenticated; bind server to localhost or protected network.
    """
    now = datetime.now(timezone.utc)
    # 1. Read-time expiry on pending approvals
    batch_expire_pending_approvals(db, now=now)

    query = db.query(Approval)
    if status_filter:
        query = query.filter(Approval.status == status_filter)

    records = query.order_by(desc(Approval.requested_at)).offset(offset).limit(limit).all()
    return [_build_approval_response(a, now) for a in records]


@router.get("/{approval_id}", response_model=ApprovalResponse)
def get_approval(
    approval_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieves an approval by ID with read-time timeout check.
    If the timeout has passed, marks the approval as 'timed_out' immediately.
    """
    now = datetime.now(timezone.utc)
    approval = db.query(Approval).filter(Approval.id == approval_id).first()
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval '{approval_id}' not found.",
        )

    # Read-time expiry check
    expire_if_timed_out(db, approval, now=now)

    return _build_approval_response(approval, now)


@router.post("/{approval_id}/decision", response_model=ApprovalDecisionResponse)
def decide_approval(
    approval_id: str,
    decision_req: ApprovalDecisionRequest,
    admin_token: str = Depends(verify_admin_token),
    db: Session = Depends(get_db),
):
    """
    Records a human decision (approve/reject).
    Requirements:
    1. Requires X-Admin-Token header.
    2. Atomic transition: UPDATE ... WHERE status = 'pending'.
    3. If the timeout has fired, the decision is rejected and the approval remains timed_out.
    4. Repeated or conflicting decisions on the same approval are rejected (409 Conflict).
    5. 'decided_by' is self-reported and documented as unauthenticated.
    """
    now = datetime.now(timezone.utc)
    approval = db.query(Approval).filter(Approval.id == approval_id).first()
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval '{approval_id}' not found.",
        )

    # 1. Read-time expiry check before applying decision
    if expire_if_timed_out(db, approval, now=now) or approval.status == "timed_out":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approval has timed out and cannot be decided; call remains denied.",
        )

    # 2. Normalize decision status
    dec = decision_req.decision.strip().lower()
    if dec in ("approve", "approved", "allow"):
        target_status = "approved"
    elif dec in ("reject", "rejected", "deny", "denied"):
        target_status = "rejected"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid decision '{decision_req.decision}'. Must be 'approve' or 'reject'.",
        )

    # 3. Atomic update where status='pending'
    stmt = (
        update(Approval)
        .where(Approval.id == approval_id, Approval.status == "pending")
        .values(
            status=target_status,
            decided_at=now,
            decision_reason=decision_req.reason,
            decided_by=decision_req.decided_by or "admin",
        )
    )
    result = db.execute(stmt)
    db.commit()

    if result.rowcount == 0:
        db.refresh(approval)
        if approval.status == "timed_out":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Approval timed out before decision could be recorded; call remains denied.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Approval was already decided with status '{approval.status}'; double-decision refused.",
            )

    db.refresh(approval)
    return ApprovalDecisionResponse(
        id=approval.id,
        status=approval.status,
        decided_at=approval.decided_at,
        decision_reason=approval.decision_reason,
        decided_by=approval.decided_by,
    )


@router.post("/{approval_id}/consume", response_model=ApprovalConsumeResponse)
def consume_approval(
    approval_id: str,
    consume_req: ApprovalConsumeRequest,
    db: Session = Depends(get_db),
):
    """
    Atomically consumes an approved call token.
    Enforces:
    1. Single-use: an approval can be consumed exactly once.
    2. Strict call-binding: call_hash must match SHA-256 of (run_id, tool_name, tool_args).
       An approval cannot authorize a different call, different tool arguments, or a different run.
    """
    now = datetime.now(timezone.utc)
    approval = db.query(Approval).filter(Approval.id == approval_id).first()
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval '{approval_id}' not found.",
        )

    # Expiry check
    expire_if_timed_out(db, approval, now=now)

    if approval.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot consume approval with status '{approval.status}'. Must be 'approved'.",
        )

    # Validate exact call hash match
    expected_hash = compute_call_hash(
        consume_req.run_id,
        consume_req.tool_name,
        consume_req.tool_args,
    )
    if approval.call_hash != expected_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approval call_hash mismatch. This approval cannot authorize a different call, arguments, or run.",
        )

    # Atomic consume (UPDATE WHERE is_consumed = 0)
    stmt = (
        update(Approval)
        .where(
            Approval.id == approval_id,
            Approval.status == "approved",
            Approval.is_consumed == 0,
        )
        .values(is_consumed=1)
    )
    result = db.execute(stmt)
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approval has already been consumed; approvals are strictly single-use.",
        )

    return ApprovalConsumeResponse(
        valid=True,
        status="consumed",
        message="Approval validated and consumed successfully.",
    )
