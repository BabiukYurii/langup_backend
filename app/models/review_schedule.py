from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ReviewSchedule(Base, UUIDMixin, TimestampMixin):
    # Materialized due-queue entry for spaced repetition (fast 'what is due now').
    __tablename__ = "review_schedules"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    user_word_uuid = Column(UUID(as_uuid=True), ForeignKey("user_words.uuid", ondelete="CASCADE"), index=True, nullable=False)
    due_at = Column(DateTime, nullable=False, index=True)
    is_completed = Column(Boolean, nullable=False, server_default="false")
