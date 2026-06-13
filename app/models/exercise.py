from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Exercise(Base, UUIDMixin, TimestampMixin):
    # A single generated/templated exercise targeting a word (and context).
    __tablename__ = "exercises"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    word_uuid = Column(UUID(as_uuid=True), ForeignKey("words.uuid", ondelete="SET NULL"), nullable=True)
    context_uuid = Column(UUID(as_uuid=True), ForeignKey("word_contexts.uuid", ondelete="SET NULL"), nullable=True)
    exercise_type = Column(String(32), nullable=False, index=True)  # ExerciseType
    difficulty = Column(Numeric(4, 2), nullable=True)  # DifficultyLevel score
    prompt = Column(Text, nullable=True)  # question/instruction text
    payload = Column(JSONB, nullable=False)  # type-specific data (options, blanks, pairs, ...)
    answer = Column(JSONB, nullable=False)  # correct answer key (hidden from client)
    is_ai_generated = Column(Boolean, nullable=False, server_default="false")
    generation_uuid = Column(UUID(as_uuid=True), ForeignKey("ai_generations.uuid", ondelete="SET NULL"), nullable=True)
