import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from server.app.database import Base


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    span_id = Column(String(36), ForeignKey("spans.id", ondelete="CASCADE"), nullable=True, index=True)
    tool_name = Column(String(255), nullable=False)
    tool_args = Column(JSON, nullable=True, default=dict)
    call_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(50), default="pending", nullable=False, index=True)  # pending | approved | rejected | timed_out
    timeout_seconds = Column(Integer, default=60, nullable=False)
    requested_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    decided_at = Column(DateTime, nullable=True)
    decision_reason = Column(String(255), nullable=True)
    decided_by = Column(String(255), nullable=True)
    is_consumed = Column(Integer, default=0, nullable=False)

    run = relationship("Run", back_populates="approvals")
    span = relationship("Span", back_populates="approvals")
