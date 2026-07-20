from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.enums.learning import ExerciseType
from app.enums.user import RoleEnum, UserStatus


class AdminUserUpdate(BaseModel):
    # Only what an admin manages; profile fields stay the user's own business.
    role: RoleEnum | None = None
    status: UserStatus | None = None


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
