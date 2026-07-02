from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import contains_eager

from app.models import UserWord, Word
from app.repositories.base import BaseRepository


class UserWordRepository(BaseRepository[UserWord]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=UserWord)

    async def get_by_user_word(self, user_id: int, word_uuid: UUID) -> UserWord | None:
        return await self.get_one(user_id=user_id, word_uuid=word_uuid)

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
    ) -> tuple[list[UserWord], int]:
        offset = (page - 1) * limit

        stmt = (
            select(UserWord)
            .join(Word, UserWord.word_uuid == Word.uuid)
            .options(contains_eager(UserWord.word))
            .where(UserWord.user_id == user_id)
        )
        count_stmt = select(func.count()).select_from(UserWord).where(UserWord.user_id == user_id)

        if query:
            cond = Word.lemma.ilike(f"{query}%")
            stmt = stmt.where(cond)
            count_stmt = count_stmt.join(Word, UserWord.word_uuid == Word.uuid).where(cond)

        stmt = stmt.order_by(UserWord.created_at.desc()).offset(offset).limit(limit)

        rows = (await self.session.execute(stmt)).unique().scalars().all()
        total = (await self.session.execute(count_stmt)).scalar() or 0
        return list(rows), total
