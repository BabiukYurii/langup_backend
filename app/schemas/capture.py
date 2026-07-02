from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.enums.vocabulary import MasteryLevel


class CaptureRequest(BaseModel):
    # Structured payload emitted by the browser extension / cabinet.
    word: str = Field(min_length=1, max_length=128)
    language: str = Field(min_length=2, max_length=8)
    sentence: str | None = None
    source_url: str | None = None
    source_title: str | None = None


class UserWordOut(BaseModel):
    # One entry of the user's personal vocabulary (UserWord + its Word).
    uuid: UUID
    lemma: str
    language: str
    part_of_speech: str | None
    mastery_level: MasteryLevel
    created_at: datetime

    @classmethod
    def from_user_word(cls, uw) -> "UserWordOut":
        return cls(
            uuid=uw.uuid,
            lemma=uw.word.lemma,
            language=uw.word.language,
            part_of_speech=uw.word.part_of_speech,
            mastery_level=uw.mastery_level,
            created_at=uw.created_at,
        )
