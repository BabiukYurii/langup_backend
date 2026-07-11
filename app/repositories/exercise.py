from uuid import UUID

from sqlalchemy import func, select

from app.enums.learning import ExerciseStatus
from app.models import Exercise
from app.repositories.base import BaseRepository


class ExerciseRepository(BaseRepository[Exercise]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=Exercise)

    async def get_for_user(self, user_id: int, uuid: UUID) -> Exercise | None:
        return await self.get_one(user_id=user_id, uuid=uuid)

    _PENDING = (ExerciseStatus.READY.value, ExerciseStatus.SERVED.value)

    async def next_pending(self, user_id: int) -> Exercise | None:
        # Served-but-unanswered first (so a page refresh re-serves the same
        # exercise instead of burning a new one), then the oldest READY item.
        stmt = (
            select(Exercise)
            .where(Exercise.user_id == user_id, Exercise.status.in_(self._PENDING))
            .order_by((Exercise.status == ExerciseStatus.READY.value).asc(), Exercise.created_at.asc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def count_pending(self, user_id: int) -> int:
        # Unanswered inventory (READY + SERVED) — what replenish tops up to target.
        stmt = (
            select(func.count())
            .select_from(Exercise)
            .where(Exercise.user_id == user_id, Exercise.status.in_(self._PENDING))
        )
        return (await self.session.execute(stmt)).scalar() or 0
