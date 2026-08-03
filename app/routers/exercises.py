from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.security.rate_limit import generation_rate_limit
from app.dependencies import CurrentUserDep, ExercisePoolServiceDep, VerifiedUserDep
from app.enums.learning import ExerciseType
from app.schemas.exercise import (
    AttemptResultOut,
    ExerciseOut,
    ExercisePreferences,
    GenerationQuotaOut,
    RefillResultOut,
    RefillStatusOut,
    SubmitAttemptRequest,
)
from app.services.learning.background import enqueue_refill, refill_task_status

router = APIRouter(prefix="/exercises", tags=["Exercises"])


@router.get("/preferences", response_model=ExercisePreferences)
async def get_preferences(
    current_user: CurrentUserDep,
    exercise_service: ExercisePoolServiceDep,
) -> ExercisePreferences:
    """Which exercise types the pool generates for me (all of them by default)."""
    return await exercise_service.get_preferences(current_user.id)


@router.get("/quota", response_model=GenerationQuotaOut)
async def generation_quota(
    current_user: CurrentUserDep,
    exercise_service: ExercisePoolServiceDep,
) -> GenerationQuotaOut:
    """My daily AI-generation quota (unlimited for active subscribers)."""
    return GenerationQuotaOut(**await exercise_service.usage.generation_quota(current_user.id))


@router.put("/preferences", response_model=ExercisePreferences)
async def set_preferences(
    data: ExercisePreferences,
    current_user: CurrentUserDep,
    exercise_service: ExercisePoolServiceDep,
) -> ExercisePreferences:
    """Choose which exercise types to practise; disabled ones leave the pool."""
    return await exercise_service.set_preferences(current_user.id, data)


@router.post("/refill", response_model=RefillResultOut, dependencies=[Depends(generation_rate_limit)])
async def refill_pool(
    current_user: VerifiedUserDep,
    exercise_service: ExercisePoolServiceDep,
    exercise_type: ExerciseType | None = None,
    language: str | None = None,
) -> RefillResultOut:
    """Generate exercises on demand.

    The pool normally refills after a word is captured; this lets a user who
    has answered everything ask for more without saving a new word. Pass
    `exercise_type` to get that specific kind. Generation is CPU-bound, so the
    request can take a while.
    """
    task_id = enqueue_refill(current_user.id, exercise_type, language)
    if task_id:
        return RefillResultOut(status="queued", task_id=task_id)
    # No worker: generating inline keeps the button working, at the cost of a
    # request that can run for a while.
    created = await exercise_service.replenish(current_user.id, exercise_type, language)
    return RefillResultOut(status="done", created=created)


@router.get("/refill/{task_id}", response_model=RefillStatusOut)
async def refill_status(task_id: str, current_user: CurrentUserDep) -> RefillStatusOut:
    """Progress of a queued refill, so the UI can poll instead of waiting."""
    return refill_task_status(task_id)


@router.get("/next", response_model=ExerciseOut)
async def next_exercise(
    current_user: VerifiedUserDep,
    exercise_service: ExercisePoolServiceDep,
    exercise_type: ExerciseType | None = None,
    language: str | None = None,
) -> ExerciseOut:
    """Serve the next pre-generated exercise from MY pool (404 if empty).

    Pass `exercise_type` to practise one specific type, `language` to practise a
    specific language (defaults to your current one).
    """
    return await exercise_service.get_next(current_user.id, exercise_type, language)


@router.post("/{exercise_uuid}/attempt", response_model=AttemptResultOut)
async def submit_attempt(
    exercise_uuid: UUID,
    data: SubmitAttemptRequest,
    current_user: CurrentUserDep,
    exercise_service: ExercisePoolServiceDep,
) -> AttemptResultOut:
    """Answer an exercise; grades it and feeds the result into spaced repetition."""
    return await exercise_service.submit_attempt(current_user.id, exercise_uuid, data)
