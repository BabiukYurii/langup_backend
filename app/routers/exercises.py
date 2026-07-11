from uuid import UUID

from fastapi import APIRouter

from app.dependencies import CurrentUserDep, ExercisePoolServiceDep
from app.schemas.exercise import AttemptResultOut, ExerciseOut, SubmitAttemptRequest

router = APIRouter(prefix="/exercises", tags=["Exercises"])


@router.get("/next", response_model=ExerciseOut)
async def next_exercise(
    current_user: CurrentUserDep,
    exercise_service: ExercisePoolServiceDep,
) -> ExerciseOut:
    """Serve the next pre-generated exercise from MY pool (404 if empty)."""
    return await exercise_service.get_next(current_user.id)


@router.post("/{exercise_uuid}/attempt", response_model=AttemptResultOut)
async def submit_attempt(
    exercise_uuid: UUID,
    data: SubmitAttemptRequest,
    current_user: CurrentUserDep,
    exercise_service: ExercisePoolServiceDep,
) -> AttemptResultOut:
    """Answer an exercise; grades it and feeds the result into spaced repetition."""
    return await exercise_service.submit_attempt(current_user.id, exercise_uuid, data)
