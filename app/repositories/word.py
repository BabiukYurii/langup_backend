from sqlalchemy import func, select

from app.models import Word
from app.repositories.base import BaseRepository


class WordRepository(BaseRepository[Word]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=Word)

    async def get_by_lemma_language(self, lemma: str, language: str) -> Word | None:
        return await self.get_one(lemma=lemma, language=language)

    async def get_by_lemmas(self, lemmas: list[str], language: str) -> list[Word]:
        """Fetch every existing word for a batch of lemmas in one query (bulk import)."""
        if not lemmas:
            return []
        stmt = select(Word).where(Word.language == language, Word.lemma.in_(lemmas))
        return list((await self.session.execute(stmt)).scalars().all())

    async def languages_with_counts(self) -> list[tuple[str, int]]:
        """Every language present in the shared dictionary with its word count."""
        stmt = select(Word.language, func.count()).group_by(Word.language).order_by(func.count().desc())
        return [(lang, count) for lang, count in (await self.session.execute(stmt)).all()]

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
