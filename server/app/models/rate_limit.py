import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint
from server.app.database import Base


class RateLimitCounter(Base):
    __tablename__ = "rate_limit_counters"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = Column(String(255), nullable=False)
    call_count = Column(Integer, default=1, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("run_id", "tool_name", name="uq_run_tool_rate_limit"),
    )
