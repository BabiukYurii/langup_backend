from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ExerciseAttempt(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "exercise_attempts"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    exercise_uuid = Column(UUID(as_uuid=True), ForeignKey("exercises.uuid", ondelete="CASCADE"), index=True, nullable=False)
    session_uuid = Column(UUID(as_uuid=True), ForeignKey("learning_sessions.uuid", ondelete="SET NULL"), nullable=True)
    submitted_answer = Column(JSONB, nullable=True)
    result = Column(String(16), nullable=False)  # AttemptResult (CORRECT/INCORRECT/SKIPPED)
    score = Column(Numeric(5, 2), nullable=True)
    quality = Column(Integer, nullable=True)  # 0..5 grade fed into SM-2
    response_time_ms = Column(Integer, nullable=True)  # for timed challenges
