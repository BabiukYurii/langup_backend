from uuid import UUID

from fastapi import APIRouter

from app.dependencies import CurrentUserDep, ReviewServiceDep
from app.schemas.learning import DueWordOut, ReviewRequest, ReviewResultOut

router = APIRouter(prefix="/review", tags=["Review"])


@router.get("/next", response_model=list[DueWordOut])
async def next_due(
    current_user: CurrentUserDep,
    review_service: ReviewServiceDep,
    limit: int = 20,
) -> list[DueWordOut]:
    """Words due for review now (new words and ones past their due date)."""
    return await review_service.get_due(current_user.id, limit)


@router.post("/{user_word_uuid}", response_model=ReviewResultOut)
async def submit_review(
    user_word_uuid: UUID,
    data: ReviewRequest,
    current_user: CurrentUserDep,
    review_service: ReviewServiceDep,
) -> ReviewResultOut:
    """Grade a review (0-5); recomputes the SM-2 interval and next due date."""
    return await review_service.review(current_user.id, user_word_uuid, data.quality)
