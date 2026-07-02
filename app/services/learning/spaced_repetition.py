from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exc import ObjectNotFoundException
from app.database.postgres import get_session
from app.enums.vocabulary import MasteryLevel
from app.repositories.user_word import UserWordRepository
from app.schemas.learning import DueWordOut, ReviewResultOut


def _utcnow() -> datetime:
    # Naive UTC to match the DB's timezone-less DateTime columns.
    return datetime.now(UTC).replace(tzinfo=None)


class SpacedRepetitionService:
    """SM-2 scheduler over UserWord state."""

    def __init__(self, session: AsyncSession) -> None:
        self.user_words = UserWordRepository(session)

    async def get_due(self, user_id: int, limit: int = 20) -> list[DueWordOut]:
        rows = await self.user_words.list_due(user_id, _utcnow(), limit)
        return [DueWordOut.from_user_word(uw) for uw in rows]

    async def review(self, user_id: int, user_word_uuid: UUID, quality: int) -> ReviewResultOut:
        uw = await self.user_words.get_for_user(user_id, user_word_uuid)
        if not uw:
            raise ObjectNotFoundException(user_word_uuid, "UserWord")

        ease = float(uw.ease_factor)
        repetitions = uw.repetitions
        interval = uw.interval_days

        # SM-2: ease factor is always updated, then interval/repetitions.
        ease = max(1.3, ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
        if quality < 3:
            repetitions = 0
            interval = 1
        else:
            if repetitions == 0:
                interval = 1
            elif repetitions == 1:
                interval = 6
            else:
                interval = round(interval * ease)
            repetitions += 1
        interval = max(1, interval)

        now = _utcnow()
        data = {
            "ease_factor": round(ease, 2),
            "repetitions": repetitions,
            "interval_days": interval,
            "last_reviewed_at": now,
            "due_at": now + timedelta(days=interval),
            "mastery_level": self._mastery(quality, repetitions, interval),
            "correct_count": uw.correct_count + (1 if quality >= 3 else 0),
            "incorrect_count": uw.incorrect_count + (0 if quality >= 3 else 1),
        }
        await self.user_words.update_one(uw, data)
        # reload with the word eagerly joined (refresh() expires the relationship)
        updated = await self.user_words.get_for_user(user_id, user_word_uuid)
        return ReviewResultOut.from_user_word(updated)

    @staticmethod
    def _mastery(quality: int, repetitions: int, interval: int) -> str:
        if quality < 3:
            return MasteryLevel.LEARNING.value
        if interval >= 21:
            return MasteryLevel.MASTERED.value
        if repetitions >= 2:
            return MasteryLevel.REVIEW.value
        return MasteryLevel.LEARNING.value


async def get_review_service(session: AsyncSession = Depends(get_session)) -> SpacedRepetitionService:
    return SpacedRepetitionService(session)
