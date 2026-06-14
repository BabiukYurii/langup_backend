from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, TimestampMixin, UUIDMixin


class WordContext(Base, UUIDMixin, TimestampMixin):
    # A concrete occurrence of a word: the sentence + surrounding context.
    __tablename__ = "word_contexts"

    word_uuid = Column(UUID(as_uuid=True), ForeignKey("words.uuid", ondelete="CASCADE"), index=True, nullable=False)
    source_uuid = Column(UUID(as_uuid=True), ForeignKey("sources.uuid", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    surface_form = Column(String(128), nullable=False)  # exact selected text
    sentence = Column(Text, nullable=False)  # sentence the word appeared in
    context_before = Column(Text, nullable=True)
    context_after = Column(Text, nullable=True)
    dom_path = Column(Text, nullable=True)  # selector path from the extension
    ai_sense = Column(JSONB, nullable=True)  # AI-resolved meaning in this context
    ai_difficulty = Column(Numeric(4, 2), nullable=True)  # AI difficulty in this context
