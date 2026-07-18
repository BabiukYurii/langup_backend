from uuid import UUID

from fastapi import APIRouter

from app.dependencies import CurrentUserDep, ExercisePoolServiceDep
from app.enums.learning import ExerciseType
from app.schemas.exercise import AttemptResultOut, ExerciseOut, ExercisePreferences, SubmitAttemptRequest

router = APIRouter(prefix="/exercises", tags=["Exercises"])


@router.get("/preferences", response_model=ExercisePreferences)
async def get_preferences(
    current_user: CurrentUserDep,
    exercise_service: ExercisePoolServiceDep,
) -> ExercisePreferences:
    """Which exercise types the pool generates for me (all of them by default)."""
    return await exercise_service.get_preferences(current_user.id)


@router.put("/preferences", response_model=ExercisePreferences)
async def set_preferences(
    data: ExercisePreferences,
    current_user: CurrentUserDep,
    exercise_service: ExercisePoolServiceDep,
) -> ExercisePreferences:
    """Choose which exercise types to practise; disabled ones leave the pool."""
    return await exercise_service.set_preferences(current_user.id, data)


@router.get("/next", response_model=ExerciseOut)
async def next_exercise(
    current_user: CurrentUserDep,
    exercise_service: ExercisePoolServiceDep,
    exercise_type: ExerciseType | None = None,
) -> ExerciseOut:
    """Serve the next pre-generated exercise from MY pool (404 if empty).

    Pass `exercise_type` to practise one specific type right now.
    """
    return await exercise_service.get_next(current_user.id, exercise_type)


@router.post("/{exercise_uuid}/attempt", response_model=AttemptResultOut)
async def submit_attempt(
    exercise_uuid: UUID,
    data: SubmitAttemptRequest,
    current_user: CurrentUserDep,
    exercise_service: ExercisePoolServiceDep,
) -> AttemptResultOut:
    """Answer an exercise; grades it and feeds the result into spaced repetition."""
    return await exercise_service.submit_attempt(current_user.id, exercise_uuid, data)
