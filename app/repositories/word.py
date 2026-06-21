from sqlalchemy import func, select

from app.models import Word
from app.repositories.base import BaseRepository


class WordRepository(BaseRepository[Word]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=Word)

    async def get_by_lemma_language(self, lemma: str, language: str) -> Word | None:
        return await self.get_one(lemma=lemma, language=language)

    async def search(
        self,
        page: int = 1,
        limit: int = 20,
        language: str | None = None,
        query: str | None = None,
    ) -> tuple[list[Word], int]:
        """List words with optional language filter and case-insensitive lemma search."""
        conditions = []
        if language:
            conditions.append(Word.language == language)
        if query:
            conditions.append(Word.lemma.ilike(f"{query}%"))

        offset = (page - 1) * limit
        stmt = select(Word).where(*conditions).order_by(Word.lemma).offset(offset).limit(limit)
        total_stmt = select(func.count()).select_from(Word).where(*conditions)

        rows = (await self.session.execute(stmt)).scalars().all()
        total = (await self.session.execute(total_stmt)).scalar() or 0
        return list(rows), total
