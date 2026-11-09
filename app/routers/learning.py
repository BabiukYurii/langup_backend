from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres import get_session
from app.dependencies import CurrentUserDep, ReviewServiceDep
from app.repositories.exercise_attempt import ExerciseAttemptRepository
from app.schemas.learning import DueWordOut, ReviewRequest, ReviewResultOut, StreakOut
from app.services.learning.streak import (
    HISTORY_DAYS,
    current_streak,
    days_left,
    local_days,
    longest_streak,
)

router = APIRouter(prefix="/review", tags=["Review"])


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/streak", response_model=StreakOut)
async def practice_streak(
    current_user: CurrentUserDep,
    session: SessionDep,
    tz_offset_minutes: Annotated[int, Query(ge=-840, le=840)] = 0,
) -> StreakOut:
    """How many days in a row the learner has practised.

    `tz_offset_minutes` is the client's own offset from UTC, because which day
    an attempt belongs to is decided at the learner's midnight, not the
    server's: practising at half past midnight in Kyiv is the previous day in
    UTC and would otherwise break a streak they had in fact kept.

    Computed on read rather than kept in a counter — there is nothing to drift,
    nothing to migrate, and a reinstall cannot lose it.
    """
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=HISTORY_DAYS)
    stamps = await ExerciseAttemptRepository(session).practice_times(current_user.id, since)
    active = local_days(stamps, tz_offset_minutes)
    today = (datetime.now(UTC) + timedelta(minutes=tz_offset_minutes)).date()

    return StreakOut(
        current=current_streak(active, today),
        longest=longest_streak(active),
        practised_today=today in active,
        days_left=days_left(active, today),
    )


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
