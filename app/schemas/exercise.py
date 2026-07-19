from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.enums.learning import SUPPORTED_EXERCISE_TYPES, AttemptResult, ExerciseType


class ExerciseOut(BaseModel):
    # One exercise served from the pool. The answer key is never included.
    uuid: UUID
    exercise_type: ExerciseType
    prompt: str | None
    difficulty: float | None
    payload: dict  # e.g. {"text": "... ___1___ ...", "blanks": [{"index": 1, "options": [...]}]}
    created_at: datetime

    @classmethod
    def from_exercise(cls, ex) -> "ExerciseOut":
        return cls(
            uuid=ex.uuid,
            exercise_type=ex.exercise_type,
            prompt=ex.prompt,
            difficulty=float(ex.difficulty) if ex.difficulty is not None else None,
            payload=ex.payload,
            created_at=ex.created_at,
        )


class SubmitAttemptRequest(BaseModel):
    # Chosen/typed word per blank index, e.g. {"1": "resilient"}.
    answers: dict[str, str] = Field(default_factory=dict)
    response_time_ms: int | None = Field(default=None, ge=0)
    # Wrong taps in a match-pairs round; ignored by the other types.
    mistakes: int | None = Field(default=None, ge=0)


class AttemptResultOut(BaseModel):
    exercise_uuid: UUID
    result: AttemptResult
    is_correct: bool
    correct_answers: dict[str, str]  # index -> correct word (revealed after answering)
    mastery_level: str | None = None  # updated SM-2 mastery, if the word was in the user's vocabulary


class ExercisePreferences(BaseModel):
    # Which exercise types the pool is allowed to generate for this user.
    exercise_types: list[ExerciseType] = Field(min_length=1)

    @field_validator("exercise_types")
    @classmethod
    def _supported_only(cls, value: list[ExerciseType]) -> list[ExerciseType]:
        # Keep the caller's order but drop repeats — the pool rotates through this list.
        unique = list(dict.fromkeys(value))
        # Accepting a planned-but-unimplemented type would silently stall the
        # pool: every generation attempt would fail and be skipped.
        unsupported = [t for t in unique if t not in SUPPORTED_EXERCISE_TYPES]
        if unsupported:
            raise ValueError(f"Unsupported exercise types: {', '.join(unsupported)}")
        return unique
