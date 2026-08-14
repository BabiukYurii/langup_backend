from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security.password import validate_password_strength
from app.enums.learning import ExerciseStatus, ExerciseType
from app.enums.user import RoleEnum, UserStatus


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None
    role: RoleEnum = RoleEnum.USER
    status: UserStatus = UserStatus.ACTIVE

    _check_password = field_validator("password")(validate_password_strength)


class AdminUserUpdate(BaseModel):
    # Only what an admin manages; profile fields plus role/status.
    role: RoleEnum | None = None
    status: UserStatus | None = None
    full_name: str | None = None
    native_language: str | None = None
    target_language: str | None = None


class AdminVocabularyAdd(BaseModel):
    word: str = Field(min_length=1, max_length=128)
    language: str = Field(min_length=2, max_length=8)


class AdminWordUpdate(BaseModel):
    # Edits the SHARED dictionary entry — visible to every user who has this
    # word. lemma changes are rejected if they collide with an existing entry.
    lemma: str | None = Field(default=None, min_length=1, max_length=128)
    translation: str | None = Field(default=None, max_length=256)
    translation_lang: str = Field(default="uk", min_length=2, max_length=8)


class AdminWordCreate(BaseModel):
    # Adds a new SHARED dictionary entry. lemma is normalized; a collision with
    # an existing lemma+language is rejected.
    lemma: str = Field(min_length=1, max_length=128)
    language: str = Field(min_length=2, max_length=8)
    translation: str | None = Field(default=None, max_length=256)
    translation_lang: str = Field(default="uk", min_length=2, max_length=8)


class AdminWordOut(BaseModel):
    uuid: UUID
    lemma: str
    language: str
    part_of_speech: str | None
    definitions: list | None

    model_config = ConfigDict(from_attributes=True)


class AdminExerciseUpdate(BaseModel):
    status: ExerciseStatus


class AdminExerciseOut(BaseModel):
    # Admin view of a stored exercise — unlike ExerciseOut it includes the
    # answer key and lifecycle fields, since this is a moderation view.
    uuid: UUID
    exercise_type: ExerciseType
    status: str
    prompt: str | None
    payload: dict
    answer: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
