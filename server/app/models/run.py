import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from server.app.database import Base


class Run(Base):
    __tablename__ = "runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    api_key_id = Column(String(36), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    task_id = Column(String(255), nullable=True, index=True)
    prompt_version = Column(String(100), nullable=True, index=True)
    model = Column(String(100), nullable=True, index=True)
    outcome = Column(String(50), default="success", nullable=False, index=True)
    failure_category = Column(String(50), nullable=True, index=True)
    total_cost = Column(Float, nullable=True, default=None)
    total_tokens = Column(Integer, default=0, nullable=False)
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    latency_ms = Column(Integer, default=0, nullable=False)
    step_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True, default=dict)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    ended_at = Column(DateTime, nullable=True)

    session = relationship("SessionModel", back_populates="runs")
    spans = relationship("Span", back_populates="run", cascade="all, delete-orphan", order_by="Span.started_at")
    approvals = relationship("Approval", back_populates="run", cascade="all, delete-orphan")
