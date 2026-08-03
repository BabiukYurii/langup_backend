import asyncio
import logging

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.exc import BadRequestException, ObjectNotFoundException
from app.database.postgres import get_session
from app.enums.vocabulary import SourceType
from app.repositories.source import SourceRepository
from app.repositories.user import UserRepository
from app.repositories.user_word import UserWordRepository
from app.repositories.word import WordRepository
from app.repositories.word_context import WordContextRepository
from app.schemas.capture import CaptureRequest, LanguageCountOut, UserWordDetailOut, UserWordOut
from app.schemas.pagination import Page
from app.services.vocabulary.translation_service import cached_translation
from app.utils.lemmatize import to_lemma

logger = logging.getLogger(__name__)

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

        # The extension only sends a hint ("en"); ask the AI what language the
        # word really is so words group by their true language. Falls back to
        # the hint if detection is off or the gateway is slow/unavailable.
        surface = data.word.strip()
        language = await self._detect_language(surface, data.sentence, data.language)

        # "I'm learning" is the language of the words you save. Set it on the
        # first capture so the profile reflects reality without asking.
        if not user.target_language:
            await self.users.update_one(user, {"target_language": language})

        # The shared dictionary is keyed by lemma, so "demands" and "demanded"
        # land on one Word; the form actually captured lives in the context.
        lemma = to_lemma(surface, language)

        word = await self.words.get_by_lemma_language(lemma, language)
        if not word:
            word = await self.words.create_one({"lemma": lemma, "language": language})

        source = None
        if data.source_url:
            source = await self.sources.get_by_user_url(user_id, data.source_url)
            if not source:
                source = await self.sources.create_one(
                    {
                        "user_id": user_id,
                        "url": data.source_url,
                        "title": data.source_title,
                        "language": language,
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

    async def _detect_language(self, word: str, sentence: str | None, fallback: str) -> str:
        """The captured word's language per the AI, or the extension's hint.

        Best-effort: gated by a flag (off in tests/CI), given a short timeout,
        and any failure falls back to the hint — a save must never hang or fail
        because language detection was slow or the gateway was down.
        """
        if not settings.exercises.DETECT_LANGUAGE_ON_CAPTURE:
            return fallback
        from app.services.ai.client import AIClient
        from app.services.ai.exercise_generation import ExerciseGenerationService

        timeout = settings.exercises.DETECT_LANGUAGE_TIMEOUT_SECONDS
        try:
            detector = ExerciseGenerationService(AIClient(timeout=timeout))
            code = await asyncio.wait_for(detector.detect_language(word, sentence), timeout=timeout + 1)
        except Exception:  # noqa: BLE001 — detection is best-effort, never blocks a save
            logger.warning("Language detection failed for %r; using hint %r", word, fallback)
            return fallback
        return code or fallback

    async def get_detail(self, user_id: int, user_word_uuid) -> UserWordDetailOut:
        """One personal entry with its cached translation and saved sentences."""
        uw = await self.user_words.get_for_user(user_id, user_word_uuid)
        if not uw:
            raise ObjectNotFoundException(user_word_uuid, "UserWord")
        user = await self.users.get_by_id(user_id)
        translation = cached_translation(uw.word, user.native_language) if user and user.native_language else None
        contexts = await self.contexts.list_for_user_word(user_id, uw.word_uuid)
        return UserWordDetailOut.build(uw, translation, contexts)

    async def remove(self, user_id: int, user_word_uuid) -> None:
        """Remove a word from THIS user's dictionary (and their saved sentences
        for it). The shared Word row is left alone — others may still have it."""
        uw = await self.user_words.get_for_user(user_id, user_word_uuid)
        if not uw:
            raise ObjectNotFoundException(user_word_uuid, "UserWord")
        await self.contexts.delete_by(user_id=user_id, word_uuid=uw.word_uuid)
        await self.user_words.delete_one(uw)

    async def list_languages(self, user_id: int) -> list[LanguageCountOut]:
        """The languages the user is learning (distinct word languages) + counts."""
        rows = await self.user_words.languages_for_user(user_id)
        return [LanguageCountOut(language=lang, count=count) for lang, count in rows]

    async def list_vocabulary(
        self,
        user_id: int,
        page: int = 1,
        limit: int = 20,
        query: str | None = None,
        language: str | None = None,
    ) -> Page[UserWordOut]:
        rows, total = await self.user_words.list_for_user(
            user_id, page=page, limit=limit, query=query, language=language
        )
        return Page[UserWordOut](
            items=[UserWordOut.from_user_word(uw) for uw in rows],
            total=total,
            page=page,
            limit=limit,
        )


async def get_capture_service(session: AsyncSession = Depends(get_session)) -> CaptureService:
    return CaptureService(session)
