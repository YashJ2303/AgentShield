from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any
from datetime import datetime
from server.app.schemas.common import Outcome, SpanType


class SpanResponse(BaseModel):
    id: str
    run_id: str
    sequence_number: int = 0
    parent_span_id: Optional[str] = None

    policy_version_id: Optional[str] = None
    span_type: str
    name: str
    input_payload: Optional[Any] = None
    output_payload: Optional[Any] = None
    latency_ms: int = 0
    token_counts: Optional[dict[str, int]] = None
    error: Optional[str] = None
    redaction_count: int = 0
    policy_decision: Optional[str] = None
    policy_rule_id: Optional[str] = None
    injection_flag: bool = False
    injection_details: Optional[dict[str, Any]] = None
    started_at: datetime
    ended_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RunResponse(BaseModel):
    id: str
    session_id: Optional[str] = None
    external_session_id: Optional[str] = None
    api_key_id: Optional[str] = None
    agent_label: Optional[str] = None
    task_id: Optional[str] = None
    prompt_version: Optional[str] = None
    model: Optional[str] = None
    outcome: str
    failure_category: Optional[str] = None
    total_cost: Optional[float] = None
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    step_count: int = 0
    error_message: Optional[str] = None
    tags: Optional[dict[str, Any]] = None
    started_at: datetime
    ended_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)



class RunDetailResponse(RunResponse):
    spans: list[SpanResponse] = Field(default_factory=list)


class RunListResponse(BaseModel):
    total: int
    runs: list[RunResponse]
