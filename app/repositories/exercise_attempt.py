from datetime import datetime

from sqlalchemy import select

from app.models import ExerciseAttempt
from app.repositories.base import BaseRepository


class ExerciseAttemptRepository(BaseRepository[ExerciseAttempt]):
    async def practice_times(self, user_id: int, since: datetime) -> list[datetime]:
        """When this user answered anything, from `since` onwards.

        Timestamps, not dates: which day an attempt belongs to depends on the
        learner's own timezone, and only the caller knows that. One column and a
        bounded window, so this stays cheap on an account with a long history.
        """
        stmt = (
            select(ExerciseAttempt.created_at)
            .where(ExerciseAttempt.user_id == user_id, ExerciseAttempt.created_at >= since)
            .order_by(ExerciseAttempt.created_at.asc())
        )
        return [row for row in (await self.session.execute(stmt)).scalars().all() if row is not None]

    def __init__(self, session) -> None:
        super().__init__(session=session, model=ExerciseAttempt)
