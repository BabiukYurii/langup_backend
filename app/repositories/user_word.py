from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import contains_eager

from app.models import UserWord, Word
from app.repositories.base import BaseRepository


class UserWordRepository(BaseRepository[UserWord]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=UserWord)

    async def get_by_user_word(self, user_id: int, word_uuid: UUID) -> UserWord | None:
        return await self.get_one(user_id=user_id, word_uuid=word_uuid)

    async def get_for_user(self, user_id: int, uuid: UUID) -> UserWord | None:
        stmt = (
            select(UserWord)
            .join(Word, UserWord.word_uuid == Word.uuid)
            .options(contains_eager(UserWord.word))
            .where(UserWord.user_id == user_id, UserWord.uuid == uuid)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def list_due(
        self, user_id: int, now: datetime, limit: int = 20, language: str | None = None
    ) -> list[UserWord]:
        # New words (due_at IS NULL) and words whose due date has passed, soonest first.
        stmt = (
            select(UserWord)
            .join(Word, UserWord.word_uuid == Word.uuid)
            .options(contains_eager(UserWord.word))
            .where(UserWord.user_id == user_id)
            .where(or_(UserWord.due_at.is_(None), UserWord.due_at <= now))
            .order_by(UserWord.due_at.is_(None).desc(), UserWord.due_at.asc())
            .limit(limit)
        )
        if language:
            stmt = stmt.where(Word.language == language)
        rows = (await self.session.execute(stmt)).unique().scalars().all()
        return list(rows)

    async def languages_for_user(self, user_id: int) -> list[tuple[str, int]]:
        """Distinct languages in the user's vocabulary with word counts, most
        words first — the set of languages they can practise."""
        stmt = (
            select(Word.language, func.count())
            .join(UserWord, UserWord.word_uuid == Word.uuid)
            .where(UserWord.user_id == user_id)
            .group_by(Word.language)
            .order_by(func.count().desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [(lang, count) for lang, count in rows]

    async def lemma_states_for_user(self, user_id: int, language: str) -> dict[str, str]:
        """Map each lemma the user has in `language` to its mastery_level, in one
        query — lets song words be split into known (MASTERED) vs learning."""
        stmt = (
            select(Word.lemma, UserWord.mastery_level)
            .join(UserWord, UserWord.word_uuid == Word.uuid)
            .where(UserWord.user_id == user_id, Word.language == language)
        )
        return dict((await self.session.execute(stmt)).all())

    async def get_with_word(self, uuid: UUID) -> UserWord | None:
        stmt = (
            select(UserWord)
            .join(Word, UserWord.word_uuid == Word.uuid)
            .options(contains_eager(UserWord.word))
            .where(UserWord.uuid == uuid)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: int,
        page: int = 1,
        limit: int = 20,
        query: str | None = None,
        language: str | None = None,
    ) -> tuple[list[UserWord], int]:
        offset = (page - 1) * limit

        stmt = (
            select(UserWord)
            .join(Word, UserWord.word_uuid == Word.uuid)
            .options(contains_eager(UserWord.word))
            .where(UserWord.user_id == user_id)
        )
        count_stmt = (
            select(func.count()).select_from(UserWord).join(Word, UserWord.word_uuid == Word.uuid)
            if (query or language)
            else select(func.count()).select_from(UserWord)
        ).where(UserWord.user_id == user_id)

        if query:
            cond = Word.lemma.ilike(f"{query}%")
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        if language:
            stmt = stmt.where(Word.language == language)
            count_stmt = count_stmt.where(Word.language == language)

        stmt = stmt.order_by(UserWord.created_at.desc()).offset(offset).limit(limit)

        rows = (await self.session.execute(stmt)).unique().scalars().all()
        total = (await self.session.execute(count_stmt)).scalar() or 0
        return list(rows), total
