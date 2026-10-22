import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, JSON, ForeignKey
from server.app.database import Base


class RegressionSuite(Base):
    __tablename__ = "regression_suites"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True)
    run_ids = Column(JSON, nullable=False, default=list)  # list of run UUIDs
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class Replay(Base):
    __tablename__ = "replays"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    original_run_id = Column(String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)
    suite_id = Column(String(36), ForeignKey("regression_suites.id", ondelete="SET NULL"), nullable=True, index=True)
    target_model = Column(String(100), nullable=True)
    target_prompt_version = Column(String(100), nullable=True)
    candidate_policy_version_id = Column(String(36), ForeignKey("policy_versions.id", ondelete="SET NULL"), nullable=True)
    outcome = Column(String(50), nullable=False)
    fidelity_score = Column(Float, default=0.0, nullable=False)
    fidelity_truncated = Column(Float, default=0.0, nullable=False)
    cache_miss_rate = Column(Float, default=0.0, nullable=False)
    trajectory_diff = Column(JSON, nullable=True, default=dict)
    sample_results = Column(JSON, nullable=True, default=list)  # Array of sample results for multi-sample
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
