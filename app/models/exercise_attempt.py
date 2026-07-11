from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    Numeric,
    String,
)

from app.models.base import Base, JSONType, TimestampMixin, UUIDMixin, UUIDType


class ExerciseAttempt(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "exercise_attempts"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    exercise_uuid = Column(UUIDType, ForeignKey("exercises.uuid", ondelete="CASCADE"), index=True, nullable=False)
    # Links to a learning_sessions row; plain column until that table is migrated.
    session_uuid = Column(UUIDType, nullable=True)
    submitted_answer = Column(JSONType, nullable=True)
    result = Column(String(16), nullable=False)  # AttemptResult (CORRECT/INCORRECT/SKIPPED)
    score = Column(Numeric(5, 2), nullable=True)
    quality = Column(Integer, nullable=True)  # 0..5 grade fed into SM-2
    response_time_ms = Column(Integer, nullable=True)  # for timed challenges
