from uuid import UUID

from sqlalchemy import select

from app.models import WordContext
from app.repositories.base import BaseRepository


class WordContextRepository(BaseRepository[WordContext]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=WordContext)

    async def latest_sentence(self, word_uuid: UUID) -> str | None:
        """The sentence a word was most recently captured in, if any."""
        stmt = (
            select(WordContext.sentence)
            .where(WordContext.word_uuid == word_uuid, WordContext.sentence.isnot(None))
            .order_by(WordContext.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_user_word(self, user_id: int, word_uuid: UUID, limit: int = 10) -> list[WordContext]:
        """Every sentence THIS user saved the word in, most recent first."""
        stmt = (
            select(WordContext)
            .where(
                WordContext.user_id == user_id,
                WordContext.word_uuid == word_uuid,
                WordContext.sentence.isnot(None),
            )
            .order_by(WordContext.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def latest_context(self, word_uuid: UUID) -> WordContext | None:
        """The most recent captured context (sentence + surface form), if any."""
        stmt = (
            select(WordContext)
            .where(WordContext.word_uuid == word_uuid, WordContext.sentence.isnot(None))
            .order_by(WordContext.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
