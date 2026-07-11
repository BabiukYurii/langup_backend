from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.enums.learning import AttemptResult, ExerciseType


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


class AttemptResultOut(BaseModel):
    exercise_uuid: UUID
    result: AttemptResult
    is_correct: bool
    correct_answers: dict[str, str]  # index -> correct word (revealed after answering)
    mastery_level: str | None = None  # updated SM-2 mastery, if the word was in the user's vocabulary
