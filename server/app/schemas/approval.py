from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any
from datetime import datetime


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    span_id: Optional[str] = None
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    call_hash: str
    status: str  # pending | approved | rejected | timed_out
    timeout_seconds: int
    remaining_seconds: float
    requested_at: datetime
    decided_at: Optional[datetime] = None
    decision_reason: Optional[str] = None
    decided_by: Optional[str] = None
    is_consumed: bool = False


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., description="'approve' or 'reject' (or 'approved' / 'rejected')")
    reason: Optional[str] = Field(None, description="Human explanation for approval or rejection")
    decided_by: Optional[str] = Field(
        None,
        description="Self-reported username of human reviewer (unauthenticated; authenticated strictly via shared X-Admin-Token)"
    )


class ApprovalDecisionResponse(BaseModel):
    id: str
    status: str
    decided_at: datetime
    decision_reason: Optional[str] = None
    decided_by: Optional[str] = None


class ApprovalConsumeRequest(BaseModel):
    run_id: str
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)


class ApprovalConsumeResponse(BaseModel):
    valid: bool
    status: str
    message: str
