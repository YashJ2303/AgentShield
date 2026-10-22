from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any
from datetime import datetime


class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    metric: str = Field(..., description="failure_rate | avg_cost | tool_error_rate | avg_latency | loop_count")
    condition: str = Field(..., description="gt | gte | lt | lte | eq")
    threshold: float
    window_runs: int = Field(default=10, ge=1, le=1000)
    webhook_url: Optional[str] = None
    is_active: bool = True


class AlertRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    metric: str
    condition: str
    threshold: float
    window_runs: int
    webhook_url: Optional[str] = None
    is_active: bool
    last_triggered_at: Optional[datetime] = None
    created_at: datetime


class AlertEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rule_id: str
    run_id: Optional[str] = None
    message: str
    details: Optional[dict[str, Any]] = None
    created_at: datetime
