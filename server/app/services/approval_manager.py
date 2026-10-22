import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import update
from server.app.models.approval import Approval


def _normalize_numbers(obj: Any) -> Any:
    """Recursively normalize float integers (e.g. 250000.0 -> 250000) for stable JSON canonicalization."""
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    elif isinstance(obj, dict):
        return {str(k): _normalize_numbers(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_normalize_numbers(v) for v in obj]
    return obj


def compute_call_hash(run_id: str, tool_name: str, tool_args: Optional[dict[str, Any]]) -> str:
    """
    Computes a deterministic SHA-256 hash over canonical call attributes.
    Binds the approval strictly to (run_id, tool_name, tool_args).
    An approval cannot be repurposed for any different tool, arguments, or run.
    Ensures stable number canonicalization (250000 == 250000.0).
    """
    norm_args = _normalize_numbers(tool_args) if tool_args is not None else {}
    canonical_repr = {
        "run_id": str(run_id),
        "tool_name": str(tool_name),
        "tool_args": norm_args,
    }
    canonical_json = json.dumps(canonical_repr, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def expire_if_timed_out(db: Session, approval: Approval, now: Optional[datetime] = None) -> bool:
    """
    Checks an approval at read time. If status is 'pending' and the timeout
    window has elapsed, atomically transitions status to 'timed_out'.
    Returns True if the approval was expired (or already timed out).
    """
    if approval.status != "pending":
        return approval.status == "timed_out"

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    req_at = approval.requested_at
    if req_at is not None and req_at.tzinfo is None:
        req_at = req_at.replace(tzinfo=timezone.utc)

    timeout_delta = timedelta(seconds=approval.timeout_seconds)
    if req_at is not None and now > (req_at + timeout_delta):
        # Atomic transition to timed_out
        stmt = (
            update(Approval)
            .where(Approval.id == approval.id, Approval.status == "pending")
            .values(
                status="timed_out",
                decided_at=now,
                decision_reason="Approval request timed out before human decision was recorded",
            )
        )
        db.execute(stmt)
        db.commit()
        db.refresh(approval)
        return True

    return False


def batch_expire_pending_approvals(db: Session, now: Optional[datetime] = None) -> int:
    """
    Scans pending approvals and atomically marks any overdue records as 'timed_out'.
    Guarantees that unserviced approvals never linger indefinitely.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    pending_list = db.query(Approval).filter(Approval.status == "pending").all()
    expired_count = 0
    for app in pending_list:
        if expire_if_timed_out(db, app, now=now):
            expired_count += 1

    return expired_count
