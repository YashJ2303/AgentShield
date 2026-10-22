from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any
from datetime import datetime


class AnalyticsSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_runs: int = 0  # sample size n
    successful_runs: int = 0
    failed_runs: int = 0
    blocked_runs: int = 0
    timed_out_runs: int = 0
    task_completion_rate: float = 0.0
    total_cost: Optional[float] = None
    cost_per_run: Optional[float] = None
    cost_per_successful_task: Optional[float] = None  # None if successful_runs == 0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    avg_tokens_per_run: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    total_tool_calls: int = 0  # n tool calls
    tool_error_rate: float = 0.0
    repeat_call_rate: float = 0.0  # Fraction of consecutive calls to the same tool
    retry_rate: float = 0.0  # Alias for repeat_call_rate
    policy_block_rate: float = 0.0
    failure_categories: dict[str, int] = Field(default_factory=dict)


class ModelBreakdownItem(BaseModel):
    model: str
    sample_size: int  # n
    completion_rate: float
    total_cost: Optional[float] = None
    cost_per_run: Optional[float] = None
    cost_per_successful_task: Optional[float] = None
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    total_tokens: int = 0


class ToolBreakdownItem(BaseModel):
    tool_name: str
    sample_size: int  # n tool calls
    error_count: int = 0
    error_rate: float = 0.0
    repeat_call_count: int = 0
    repeat_call_rate: float = 0.0
    retry_count: int = 0  # Alias for repeat_call_count
    retry_rate: float = 0.0  # Alias for repeat_call_rate
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0
    policy_block_count: int = 0
    top_block_rule: Optional[str] = None  # most frequent denying rule id for this tool


class PromptVersionBreakdownItem(BaseModel):
    prompt_version: str
    sample_size: int  # n
    completion_rate: float
    total_cost: Optional[float] = None
    cost_per_run: Optional[float] = None
    cost_per_successful_task: Optional[float] = None
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    avg_latency_ms: float = 0.0


class TimeSeriesDataPoint(BaseModel):
    date: str
    sample_size: int  # n
    total_cost: Optional[float] = None
    avg_latency_ms: float = 0.0
    success_rate: float = 0.0
    tool_calls: int = 0  # tool spans recorded on this date
    blocked_runs: int = 0  # runs with outcome == "blocked" on this date


class AnomalyItem(BaseModel):
    id: str
    run_id: str
    type: str  # repeated_tool_loop | latency_outlier | step_count_outlier | cost_outlier
    severity: str  # low | medium | high | critical
    metric: str
    value: Any
    sample_size: Optional[int] = None  # population n for outliers
    baseline_reference: Optional[str] = None
    message: str
    detected_at: datetime


class ModelComparisonMetric(BaseModel):
    metric_name: str
    model_a_value: Optional[float] = None
    model_b_value: Optional[float] = None
    diff_percentage: Optional[float] = None
    winner: Optional[str] = None  # 'model_a' | 'model_b' | 'tie' | 'unknown'


class ModelComparisonResponse(BaseModel):
    model_a: str
    model_b: str
    model_a_sample_size: int  # n_a
    model_b_sample_size: int  # n_b
    metrics: list[ModelComparisonMetric]
    note: Optional[str] = None
