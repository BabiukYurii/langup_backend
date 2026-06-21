from sqlalchemy import (
    JSON,
    Column,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base, TimestampMixin, UUIDMixin

# JSONB on Postgres, generic JSON on sqlite (so the test suite can run on sqlite).
JSONType = JSONB().with_variant(JSON(), "sqlite")


class Word(Base, UUIDMixin, TimestampMixin):
    # Shared dictionary entry (one row per lemma+language), reused across users.
    __tablename__ = "words"
    __table_args__ = (UniqueConstraint("lemma", "language", name="uq_word_lemma_language"),)

    lemma = Column(String(128), nullable=False, index=True)  # normalized base form
    language = Column(String(8), nullable=False, index=True)  # LanguageCode
    part_of_speech = Column(String(32), nullable=True)  # PartOfSpeech
    phonetic = Column(String(128), nullable=True)  # IPA transcription
    definitions = Column(JSONType, nullable=True)  # list of senses/translations
    frequency_rank = Column(Integer, nullable=True)  # corpus frequency (difficulty signal)
    base_difficulty = Column(Numeric(4, 2), nullable=True)  # AI/heuristic base difficulty 0..10
