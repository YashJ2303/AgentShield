from pydantic import BaseModel, Field
from typing import Optional, Any


class DryRunRequest(BaseModel):
    candidate_yaml: Optional[str] = Field(None, description="Candidate YAML policy content to test")
    candidate_version_number: Optional[int] = Field(None, description="Existing policy version number to test against")
    run_ids: Optional[list[str]] = Field(None, description="Specific run IDs to evaluate against")
    limit_runs: int = Field(50, ge=1, le=500, description="Max historical runs to evaluate if run_ids not specified")


class SpanDiffItem(BaseModel):
    span_id: str
    run_id: str
    tool_name: str
    tool_args: dict[str, Any]
    original_decision: Optional[str] = None
    original_rule_id: Optional[str] = None
    candidate_decision: str
    candidate_rule_id: Optional[str] = None
    candidate_reason: Optional[str] = None
    has_changed: bool


class DryRunResponse(BaseModel):
    total_runs_evaluated: int
    total_spans_evaluated: int
    would_allow: int
    would_deny: int
    would_require_approval: int
    changed_count: int
    diffs: list[SpanDiffItem] = Field(default_factory=list)
