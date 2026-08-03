from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)

from app.models.base import Base, JSONType, TimestampMixin, UUIDMixin, UUIDType


class Exercise(Base, UUIDMixin, TimestampMixin):
    # A single generated/templated exercise targeting a word (and context).
    # Lives in a per-user pool: pre-generated (READY) -> served -> completed.
    __tablename__ = "exercises"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    word_uuid = Column(UUIDType, ForeignKey("words.uuid", ondelete="SET NULL"), nullable=True)
    context_uuid = Column(UUIDType, ForeignKey("word_contexts.uuid", ondelete="SET NULL"), nullable=True)
    exercise_type = Column(String(32), nullable=False, index=True)  # ExerciseType
    # Language being practised (the target word's language). Lets the pool be
    # served per-language when a learner studies several at once.
    language = Column(String(8), nullable=True, index=True)  # LanguageCode
    status = Column(String(16), nullable=False, server_default="READY", index=True)  # ExerciseStatus
    difficulty = Column(Numeric(4, 2), nullable=True)  # DifficultyLevel score
    prompt = Column(Text, nullable=True)  # question/instruction text
    payload = Column(JSONType, nullable=False)  # client-facing data (text, options, blanks — no answers)
    answer = Column(JSONType, nullable=False)  # correct answer key (hidden from client)
    is_ai_generated = Column(Boolean, nullable=False, server_default="false")
    # Links to the ai_generations audit row; plain column until that table is migrated.
    generation_uuid = Column(UUIDType, nullable=True)
