import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime
from server.app.database import Base


class PolicyVersion(Base):
    __tablename__ = "policy_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    version_number = Column(Integer, unique=True, nullable=False, index=True)
    yaml_content = Column(Text, nullable=False)
    change_note = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by = Column(String(255), nullable=True)
