from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres import get_session
from app.enums.vocabulary import SourceType
from app.repositories.source import SourceRepository
from app.repositories.user_word import UserWordRepository
from app.repositories.word import WordRepository
from app.repositories.word_context import WordContextRepository
from app.schemas.capture import CaptureRequest, UserWordOut
from app.schemas.pagination import Page


class CaptureService:
    """Turns a captured word into the user's personal vocabulary:
    get-or-create the shared Word, store the Source + WordContext, and link a
    UserWord to the current user."""

    def __init__(self, session: AsyncSession) -> None:
        self.words = WordRepository(session)
        self.sources = SourceRepository(session)
        self.contexts = WordContextRepository(session)
        self.user_words = UserWordRepository(session)

    async def capture(self, user_id: int, data: CaptureRequest) -> UserWordOut:
        lemma = data.word.strip()

        word = await self.words.get_by_lemma_language(lemma, data.language)
        if not word:
            word = await self.words.create_one({"lemma": lemma, "language": data.language})

        source = None
        if data.source_url:
            source = await self.sources.get_by_user_url(user_id, data.source_url)
            if not source:
                source = await self.sources.create_one(
                    {
                        "user_id": user_id,
                        "url": data.source_url,
                        "title": data.source_title,
                        "language": data.language,
                        "source_type": SourceType.WEB_PAGE.value,
                    }
                )

        if data.sentence:
            await self.contexts.create_one(
                {
                    "user_id": user_id,
                    "word_uuid": word.uuid,
                    "source_uuid": source.uuid if source else None,
                    "surface_form": lemma,
                    "sentence": data.sentence,
                }
            )

        user_word = await self.user_words.get_by_user_word(user_id, word.uuid)
        if not user_word:
            user_word = await self.user_words.create_one({"user_id": user_id, "word_uuid": word.uuid})

        user_word = await self.user_words.get_with_word(user_word.uuid)
        return UserWordOut.from_user_word(user_word)

    async def list_vocabulary(
        self,
        user_id: int,
        page: int = 1,
        limit: int = 20,
        query: str | None = None,
    ) -> Page[UserWordOut]:
        rows, total = await self.user_words.list_for_user(user_id, page=page, limit=limit, query=query)
        return Page[UserWordOut](
            items=[UserWordOut.from_user_word(uw) for uw in rows],
            total=total,
            page=page,
            limit=limit,
        )


async def get_capture_service(session: AsyncSession = Depends(get_session)) -> CaptureService:
    return CaptureService(session)
