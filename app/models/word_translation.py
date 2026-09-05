from sqlalchemy import Column, String, UniqueConstraint

from app.models.base import Base, TimestampMixin, UUIDMixin


class WordTranslation(Base, UUIDMixin, TimestampMixin):
    # One word, glossed inside the line it was met in.
    #
    # Deliberately user-independent, like audio_clips: the answer depends on the
    # word, its context and the two languages — never on who asked. So the first
    # learner to tap a word pays for the model and every learner after them
    # reads the row. That is what makes a repeated chorus, a song two people
    # share, and a whole playlist warmed ahead of time affordable on one CPU.
    #
    # `context_hash` is a hash of the line, and the line itself is NOT stored —
    # see translation_keys for why that is a rule and not an oversight.
    __tablename__ = "word_translations"
    __table_args__ = (
        UniqueConstraint(
            "word",
            "source_language",
            "target_language",
            "context_hash",
            name="uq_word_translation",
        ),
    )

    # The surface form as it appeared, not our lemma: the offline lemmatizer
    # mangles words ("straight" -> "stretch"), and a gloss for something the
    # learner never saw is worse than none.
    word = Column(String(128), nullable=False, index=True)
    source_language = Column(String(8), nullable=False, index=True)
    target_language = Column(String(8), nullable=False, index=True)
    context_hash = Column(String(64), nullable=False, index=True)
    translation = Column(String(512), nullable=False)
