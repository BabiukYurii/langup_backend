from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exc import BadRequestException
from app.database.postgres import get_session
from app.enums.vocabulary import SourceType
from app.repositories.source import SourceRepository
from app.repositories.user import UserRepository
from app.repositories.user_word import UserWordRepository
from app.repositories.word import WordRepository
from app.repositories.word_context import WordContextRepository
from app.schemas.capture import CaptureRequest, UserWordOut
from app.schemas.pagination import Page
from app.utils.lemmatize import to_lemma

# Machine-readable markers the client can match to prompt the right next step.
NATIVE_LANGUAGE_REQUIRED = "native_language_required"
EMAIL_NOT_VERIFIED = "email_not_verified"


class CaptureService:
    """Turns a captured word into the user's personal vocabulary:
    get-or-create the shared Word, store the Source + WordContext, and link a
    UserWord to the current user."""

    def __init__(self, session: AsyncSession) -> None:
        self.words = WordRepository(session)
        self.sources = SourceRepository(session)
        self.contexts = WordContextRepository(session)
        self.user_words = UserWordRepository(session)
        self.users = UserRepository(session)

    async def capture(self, user_id: int, data: CaptureRequest) -> UserWordOut:
        # A native language is mandatory before saving: it's the language we
        # translate captured words into, so without it the word is unusable.
        # Enforced here (not just in the client) so no caller can bypass it.
        user = await self.users.get_by_id(user_id)
        if not user or not user.native_language:
            raise BadRequestException(NATIVE_LANGUAGE_REQUIRED)
        # A confirmed email is required to save words: it keeps the account
        # tied to a real address. Google sign-ins arrive already verified.
        if not user.is_email_verified:
            raise BadRequestException(EMAIL_NOT_VERIFIED)

        # The shared dictionary is keyed by lemma, so "demands" and "demanded"
        # land on one Word; the form actually captured lives in the context.
        surface = data.word.strip()
        lemma = to_lemma(surface, data.language)

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
                    "surface_form": surface,
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
