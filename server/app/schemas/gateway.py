from pydantic import BaseModel, Field
from typing import Optional, Any


class CheckToolRequest(BaseModel):
    run_id: str
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    current_running_cost: float = Field(0.0, ge=0.0)
    current_total_tokens: int = Field(0, ge=0)
    current_step_count: int = Field(0, ge=0)
    elapsed_wall_time_seconds: Optional[float] = Field(
        None, description="Ignored by server; wall time is computed server-side from run's started_at in DB"
    )


class CheckToolResponse(BaseModel):
    decision: str  # allow | deny | pending | require_approval
    rule_id: Optional[str] = None
    reason: Optional[str] = None
    approval_id: Optional[str] = None
    timeout_seconds: Optional[int] = None
    call_hash: Optional[str] = None
    policy_version_id: Optional[str] = None


class InjectionMatchItem(BaseModel):
    category: str
    pattern_name: str
    detector: str
    start_offset: int
    end_offset: int
    confidence: float
    details: Optional[str] = None


class ScreenOutputRequest(BaseModel):
    run_id: str
    tool_name: str
    tool_output: Any
    span_id: Optional[str] = None


class ScreenOutputResponse(BaseModel):
    action_taken: str  # allow | block | flag | sanitize
    is_safe: bool
    injection_flag: bool
    sanitized_output: Optional[Any] = None
    matches: list[InjectionMatchItem] = Field(default_factory=list)
    reason: Optional[str] = None
