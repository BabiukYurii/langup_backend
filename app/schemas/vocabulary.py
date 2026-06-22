from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.enums.vocabulary import PartOfSpeech


class WordCreate(BaseModel):
    lemma: str = Field(min_length=1, max_length=128)
    language: str = Field(min_length=2, max_length=8)
    part_of_speech: PartOfSpeech | None = None
    phonetic: str | None = None
    definitions: list[dict] | None = None
    frequency_rank: int | None = None
    base_difficulty: float | None = Field(default=None, ge=0, le=10)


class WordUpdate(BaseModel):
    part_of_speech: PartOfSpeech | None = None
    phonetic: str | None = None
    definitions: list[dict] | None = None
    frequency_rank: int | None = None
    base_difficulty: float | None = Field(default=None, ge=0, le=10)


class WordOut(BaseModel):
    uuid: UUID
    lemma: str
    language: str
    part_of_speech: str | None
    phonetic: str | None
    definitions: list[dict] | None
    frequency_rank: int | None
    base_difficulty: float | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
