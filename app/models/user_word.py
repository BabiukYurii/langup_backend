from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class UserWord(Base, UUIDMixin, TimestampMixin):
    # A user's personal vocabulary item + spaced-repetition (SM-2) state.
    __tablename__ = "user_words"
    __table_args__ = (UniqueConstraint("user_id", "word_uuid", name="uq_user_word"),)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    word_uuid = Column(UUID(as_uuid=True), ForeignKey("words.uuid", ondelete="CASCADE"), index=True, nullable=False)
    mastery_level = Column(String(16), nullable=False, server_default="NEW")  # MasteryLevel
    ease_factor = Column(Numeric(4, 2), nullable=False, server_default="2.5")  # SM-2 ease
    interval_days = Column(Integer, nullable=False, server_default="0")  # current interval
    repetitions = Column(Integer, nullable=False, server_default="0")  # successful reps in a row
    correct_count = Column(Integer, nullable=False, server_default="0")
    incorrect_count = Column(Integer, nullable=False, server_default="0")
    last_reviewed_at = Column(DateTime, nullable=True)
    due_at = Column(DateTime, nullable=True, index=True)  # next review time

    user = relationship("User", back_populates="words")
