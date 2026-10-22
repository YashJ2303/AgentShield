from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any
from datetime import datetime


class ReplayRequest(BaseModel):
    original_run_id: str = Field(..., description="UUID of recorded baseline run to replay")
    target_model: Optional[str] = Field(None, description="Candidate model identifier")
    target_prompt: Optional[str] = Field(None, description="Altered prompt string or version")
    candidate_policy_yaml: Optional[str] = Field(None, description="Candidate YAML policy content")
    candidate_policy_version_id: Optional[str] = Field(None, description="Stored policy version ID")
    matching_threshold: float = Field(0.85, ge=0.0, le=1.0, description="Fuzzy argument matching threshold (default 0.85)")
    num_samples: int = Field(3, ge=1, le=10, description="Number of replay repetitions to evaluate spread (default 3)")
    compute_sensitivity: bool = Field(False, description="Whether to evaluate threshold sensitivity at 0.75, 0.85, 0.95")


class ReplaySampleResponse(BaseModel):
    sample_index: int
    fidelity_score: float
    fidelity_truncated: float = 0.0
    s_tool: float
    s_args: float
    s_outcome: float
    cache_miss_rate: float
    replayed_outcome: str
    replayed_tools: list[str]


class TrajectoryStepDiffResponse(BaseModel):
    step_number: int
    tool_name_recorded: Optional[str] = None
    tool_name_replayed: Optional[str] = None
    tool_match: bool
    args_recorded: Any = None
    args_replayed: Any = None
    arg_similarity: float
    output_recorded: Any = None
    output_replayed: Any = None
    policy_decision_recorded: Optional[str] = None
    policy_decision_replayed: Optional[str] = None
    is_cache_miss: bool


class SensitivityPoint(BaseModel):
    threshold: float
    fidelity_score: float
    cache_miss_rate: float
    cache_misses: int
    total_calls: int


class ReplayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    replay_id: str
    original_run_id: str
    target_model: Optional[str] = None
    target_prompt_version: Optional[str] = None
    candidate_policy_version_id: Optional[str] = None
    outcome: str
    fidelity_score: float
    fidelity_truncated: float = 0.0
    cache_miss_rate: float
    fidelity_spread: float = 0.0  # Legacy alias for range
    fidelity_range: float = 0.0   # Sample Range: max(fidelity) - min(fidelity)
    fidelity_std_dev: float = 0.0 # Sample Standard Deviation (s)
    regression_detected: bool = False
    regression_reasons: list[str] = Field(default_factory=list)
    sample_results: list[ReplaySampleResponse] = Field(default_factory=list)
    trajectory_diff: list[TrajectoryStepDiffResponse] = Field(default_factory=list)
    sensitivity_table: Optional[list[SensitivityPoint]] = None
    created_at: Optional[datetime] = None


class BatchReplayRequest(BaseModel):
    run_ids: list[str] = Field(..., min_length=1, description="List of recorded run UUIDs to replay")
    target_model: Optional[str] = Field(None, description="Candidate model identifier")
    target_prompt: Optional[str] = Field(None, description="Altered prompt string")
    candidate_policy_yaml: Optional[str] = Field(None, description="Candidate YAML policy content")
    matching_threshold: float = Field(0.85, ge=0.0, le=1.0)
    num_samples: int = Field(3, ge=1, le=10)
    compute_sensitivity: bool = Field(False)


class BatchReplayItemSummary(BaseModel):
    run_id: str
    replay_id: Optional[str] = None
    status: str  # "replayed" | "not_found" | "error"
    model: Optional[str] = None
    fidelity_score: Optional[float] = None
    fidelity_truncated: Optional[float] = None
    cache_miss_rate: Optional[float] = None
    regression_detected: bool = False
    regression_reasons: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class BatchReplayResponse(BaseModel):
    total_requested: int
    successful_replays: int
    failed_replays: int
    mean_fidelity: float
    mean_truncated_fidelity: float
    mean_cache_miss_rate: float
    regressions_detected: int
    regression_rate: float
    items: list[BatchReplayItemSummary] = Field(default_factory=list)
    missing_run_ids: list[str] = Field(default_factory=list)
    markdown_report: str
    json_report: dict[str, Any]
