from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


class SessionResponse(BaseModel):
    id: str
    session_id: str
    name: Optional[str] = None
    session_metadata: dict[str, Any] = Field(default_factory=dict)
    run_count: int = 0
    created_at: datetime


class SessionListResponse(BaseModel):
    total: int
    sessions: list[SessionResponse]
