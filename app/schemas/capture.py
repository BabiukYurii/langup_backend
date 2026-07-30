from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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
    word_uuid: UUID  # the shared dictionary entry behind this personal item
    lemma: str
    language: str
    part_of_speech: str | None
    mastery_level: MasteryLevel
    created_at: datetime

    @classmethod
    def from_user_word(cls, uw) -> "UserWordOut":
        return cls(
            uuid=uw.uuid,
            word_uuid=uw.word_uuid,
            lemma=uw.word.lemma,
            language=uw.word.language,
            part_of_speech=uw.word.part_of_speech,
            mastery_level=uw.mastery_level,
            created_at=uw.created_at,
        )


class WordContextOut(BaseModel):
    # One sentence the user saved this word in.
    sentence: str
    surface_form: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserWordDetailOut(BaseModel):
    # Full view of one personal vocabulary entry: the word, its cached
    # translation, and the sentences the user captured it in.
    uuid: UUID
    word_uuid: UUID
    lemma: str
    language: str
    part_of_speech: str | None
    mastery_level: MasteryLevel
    created_at: datetime
    translation: str | None = None
    contexts: list[WordContextOut] = []

    @classmethod
    def build(cls, uw, translation: str | None, contexts: list) -> "UserWordDetailOut":
        return cls(
            uuid=uw.uuid,
            word_uuid=uw.word_uuid,
            lemma=uw.word.lemma,
            language=uw.word.language,
            part_of_speech=uw.word.part_of_speech,
            mastery_level=uw.mastery_level,
            created_at=uw.created_at,
            translation=translation,
            contexts=[WordContextOut.model_validate(c) for c in contexts],
        )
