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

    async def next_ready(self, user_id: int) -> Exercise | None:
        # Oldest unseen exercise from the user's pool.
        stmt = (
            select(Exercise)
            .where(Exercise.user_id == user_id, Exercise.status == ExerciseStatus.READY.value)
            .order_by(Exercise.created_at.asc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def count_ready(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Exercise)
            .where(Exercise.user_id == user_id, Exercise.status == ExerciseStatus.READY.value)
        )
        return (await self.session.execute(stmt)).scalar() or 0
