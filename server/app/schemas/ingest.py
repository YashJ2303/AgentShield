from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from server.app.schemas.common import SpanType, Outcome, PolicyDecision


class SpanIngestItem(BaseModel):
    id: Optional[str] = None
    run_id: str
    sequence_number: Optional[int] = 0
    parent_span_id: Optional[str] = None

    policy_version_id: Optional[str] = None
    span_type: SpanType
    name: str
    input_payload: Optional[Any] = Field(default_factory=dict)
    output_payload: Optional[Any] = Field(default_factory=dict)
    started_at: datetime
    ended_at: Optional[datetime] = None
    latency_ms: Optional[int] = 0
    token_counts: Optional[dict[str, int]] = Field(default_factory=dict)
    error: Optional[str] = None
    policy_decision: Optional[str] = None
    policy_rule_id: Optional[str] = None
    injection_flag: Optional[bool] = False
    injection_details: Optional[dict[str, Any]] = None
    redaction_count: Optional[int] = 0


class BatchIngestRequest(BaseModel):
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    prompt_version: Optional[str] = None
    model: Optional[str] = None
    outcome: Optional[Outcome] = None
    tags: Optional[dict[str, Any]] = Field(default_factory=dict)
    spans: list[SpanIngestItem] = Field(default_factory=list)


class BatchIngestResponse(BaseModel):
    status: str = "ok"
    run_id: str
    spans_ingested: int
    redaction_count: int
    outcome: str
