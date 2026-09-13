from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, distinct, func, select

from app.enums.learning import ExerciseStatus
from app.models import Exercise
from app.repositories.base import BaseRepository


class ExerciseRepository(BaseRepository[Exercise]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=Exercise)

    async def get_for_user(self, user_id: int, uuid: UUID) -> Exercise | None:
        return await self.get_one(user_id=user_id, uuid=uuid)

    _PENDING = (ExerciseStatus.READY.value, ExerciseStatus.SERVED.value)

    async def next_pending(
        self, user_id: int, exercise_type: str | None = None, language: str | None = None
    ) -> Exercise | None:
        # Served-but-unanswered first (so a page refresh re-serves the same
        # exercise instead of burning a new one), then the oldest READY item.
        stmt = (
            select(Exercise)
            .where(Exercise.user_id == user_id, Exercise.status.in_(self._PENDING))
            .order_by((Exercise.status == ExerciseStatus.READY.value).asc(), Exercise.created_at.asc())
            .limit(1)
        )
        if exercise_type:
            stmt = stmt.where(Exercise.exercise_type == exercise_type)
        if language:
            stmt = stmt.where(Exercise.language == language)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def has_pending_of_type(self, user_id: int, exercise_type: str, language: str | None = None) -> bool:
        stmt = (
            select(Exercise.uuid)
            .where(
                Exercise.user_id == user_id,
                Exercise.status.in_(self._PENDING),
                Exercise.exercise_type == exercise_type,
            )
            .limit(1)
        )
        if language:
            stmt = stmt.where(Exercise.language == language)
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def count_pending(self, user_id: int, language: str | None = None) -> int:
        # Unanswered inventory (READY + SERVED) — what replenish tops up to target.
        stmt = (
            select(func.count())
            .select_from(Exercise)
            .where(Exercise.user_id == user_id, Exercise.status.in_(self._PENDING))
        )
        if language:
            stmt = stmt.where(Exercise.language == language)
        return (await self.session.execute(stmt)).scalar() or 0

    async def types_for_word(self, user_id: int, word_uuid: UUID) -> set[str]:
        """Exercise types already built for this word, in any status."""
        stmt = select(distinct(Exercise.exercise_type)).where(
            Exercise.user_id == user_id, Exercise.word_uuid == word_uuid
        )
        return set((await self.session.execute(stmt)).scalars().all())

    async def words_missing_types(self, user_id: int, wanted: Sequence[str], limit: int) -> list[UUID]:
        """UserWord uuids that lack at least one of `wanted` exercise types.

        Counts exercises in ANY status, because this answers "was a set ever
        built for this word", not "is there one to practise right now" — the
        pool refill owns the second question. Oldest words first, so a backlog
        is worked through in the order it accumulated.
        """
        from app.models import UserWord

        made = (
            select(Exercise.word_uuid, func.count(distinct(Exercise.exercise_type)).label("types"))
            .where(Exercise.user_id == user_id, Exercise.exercise_type.in_(wanted))
            .group_by(Exercise.word_uuid)
            .subquery()
        )
        stmt = (
            select(UserWord.uuid)
            .outerjoin(made, made.c.word_uuid == UserWord.word_uuid)
            .where(UserWord.user_id == user_id)
            .where(func.coalesce(made.c.types, 0) < len(wanted))
            .order_by(UserWord.created_at.asc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def drop_ready_of_types(self, user_id: int, exercise_types: Sequence[str]) -> int:
        """Discard not-yet-served exercises of the given types.

        Used when a user turns a type off: leaving them would occupy the pool
        (they count toward the refill target) while never being served.
        """
        if not exercise_types:
            return 0
        stmt = delete(Exercise).where(
            Exercise.user_id == user_id,
            Exercise.status == ExerciseStatus.READY.value,
            Exercise.exercise_type.in_(exercise_types),
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount or 0
