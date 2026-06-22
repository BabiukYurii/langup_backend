from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exc import ObjectAlreadyExistsException, ObjectNotFoundException
from app.database.postgres import get_session
from app.models import Word
from app.repositories.word import WordRepository
from app.schemas.pagination import Page
from app.schemas.vocabulary import WordCreate, WordOut, WordUpdate


class WordService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = WordRepository(session)

    async def create_word(self, data: WordCreate) -> WordOut:
        existing = await self.repository.get_by_lemma_language(data.lemma, data.language)
        if existing:
            raise ObjectAlreadyExistsException(f"{data.lemma} ({data.language})", "Word")
        payload = data.model_dump()
        if payload.get("part_of_speech") is not None:
            payload["part_of_speech"] = payload["part_of_speech"].value
        word = await self.repository.create_one(payload)
        return WordOut.model_validate(word)

    async def get_word(self, word_uuid: UUID) -> WordOut:
        word = await self._get_or_404(word_uuid)
        return WordOut.model_validate(word)

    async def list_words(
        self,
        page: int = 1,
        limit: int = 20,
        language: str | None = None,
        query: str | None = None,
    ) -> Page[WordOut]:
        words, total = await self.repository.search(page=page, limit=limit, language=language, query=query)
        return Page[WordOut](
            items=[WordOut.model_validate(w) for w in words],
            total=total,
            page=page,
            limit=limit,
        )

    async def update_word(self, word_uuid: UUID, data: WordUpdate) -> WordOut:
        word = await self._get_or_404(word_uuid)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("part_of_speech") is not None:
            changes["part_of_speech"] = changes["part_of_speech"].value
        updated = await self.repository.update_one(word, changes)
        return WordOut.model_validate(updated)

    async def delete_word(self, word_uuid: UUID) -> None:
        await self._get_or_404(word_uuid)
        await self.repository.delete_by(uuid=word_uuid)

    async def _get_or_404(self, word_uuid: UUID) -> Word:
        word = await self.repository.get_one(uuid=word_uuid)
        if not word:
            raise ObjectNotFoundException(word_uuid, "Word")
        return word


async def get_word_service(session: AsyncSession = Depends(get_session)) -> WordService:
    return WordService(session)
