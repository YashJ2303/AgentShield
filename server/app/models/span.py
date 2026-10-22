import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from server.app.database import Base


class Span(Base):
    __tablename__ = "spans"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence_number = Column(Integer, default=0, nullable=False, index=True)
    parent_span_id = Column(String(36), nullable=True, index=True)
    policy_version_id = Column(String(36), ForeignKey("policy_versions.id", ondelete="SET NULL"), nullable=True, index=True)

    span_type = Column(String(20), nullable=False, index=True)  # 'model' | 'tool'
    name = Column(String(255), nullable=False)
    input_payload = Column(JSON, nullable=True, default=dict)  # Full model inputs or tool args
    output_payload = Column(JSON, nullable=True, default=dict) # Model response or tool results
    latency_ms = Column(Integer, default=0, nullable=False)
    token_counts = Column(JSON, nullable=True, default=dict)
    error = Column(Text, nullable=True)
    redaction_count = Column(Integer, default=0, nullable=False)
    policy_decision = Column(String(50), nullable=True)  # allow | deny | require_approval | approved | rejected | bypassed
    policy_rule_id = Column(String(100), nullable=True)
    injection_flag = Column(Boolean, default=False, nullable=False)
    injection_details = Column(JSON, nullable=True)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    ended_at = Column(DateTime, nullable=True)

    run = relationship("Run", back_populates="spans")
    approvals = relationship("Approval", back_populates="span", cascade="all, delete-orphan")
