from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.enums.vocabulary import MasteryLevel


class ReviewRequest(BaseModel):
    # SM-2 recall quality: 0 (blackout) .. 5 (perfect).
    quality: int = Field(ge=0, le=5)


class DueWordOut(BaseModel):
    uuid: UUID
    lemma: str
    language: str
    mastery_level: MasteryLevel
    due_at: datetime | None

    @classmethod
    def from_user_word(cls, uw) -> "DueWordOut":
        return cls(
            uuid=uw.uuid,
            lemma=uw.word.lemma,
            language=uw.word.language,
            mastery_level=uw.mastery_level,
            due_at=uw.due_at,
        )


class ReviewResultOut(BaseModel):
    uuid: UUID
    lemma: str
    mastery_level: MasteryLevel
    repetitions: int
    interval_days: int
    ease_factor: float
    due_at: datetime | None

    @classmethod
    def from_user_word(cls, uw) -> "ReviewResultOut":
        return cls(
            uuid=uw.uuid,
            lemma=uw.word.lemma,
            mastery_level=uw.mastery_level,
            repetitions=uw.repetitions,
            interval_days=uw.interval_days,
            ease_factor=float(uw.ease_factor),
            due_at=uw.due_at,
        )
