from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class AIGeneration(Base, UUIDMixin, TimestampMixin):
    # Log of every AI invocation: inputs, outputs, model, cost, status.
    __tablename__ = "ai_generations"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    task_type = Column(String(32), nullable=False, index=True)  # AITaskType
    status = Column(String(16), nullable=False, server_default="PENDING")  # AIJobStatus
    model = Column(String(64), nullable=True)  # model id used
    request_payload = Column(JSONB, nullable=True)
    response_payload = Column(JSONB, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
