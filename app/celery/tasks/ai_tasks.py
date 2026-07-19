"""AI jobs that must not run inside a web request.

Generation is CPU-bound and slow, and Ollama serves one inference at a time, so
these run on a worker with a single concurrent slot. Failures retry: the model
is not deterministic, and a word it refused once usually works on a second try.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID

from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import settings
from app.enums.learning import ExerciseType

logger = logging.getLogger(__name__)

_RETRY_KWARGS = {
    "autoretry_for": (Exception,),
    "max_retries": settings.celery.CELERY_TASK_MAX_RETRIES,
    "retry_backoff": settings.celery.CELERY_RETRY_BACKOFF_SECONDS,
    "retry_jitter": True,
}


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    """A session on an engine of this task's own.

    Every task runs in a fresh event loop via asyncio.run(), and an async engine
    cannot be shared across loops — so the app-wide one is deliberately not used.
    """
    engine = create_async_engine(
        settings.db.url,
        connect_args=settings.db.connect_args,
        pool_pre_ping=True,
    )
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()


def _run(coro_factory: Callable[[AsyncSession], Awaitable[int]]) -> int:
    async def main() -> int:
        async with _session() as session:
            return await coro_factory(session)

    return asyncio.run(main())


def _pool_service(session: AsyncSession):
    # Imported lazily: the worker boots without pulling the whole web app in.
    from app.services.ai.client import AIClient
    from app.services.ai.exercise_generation import ExerciseGenerationService
    from app.services.learning.exercise_service import ExercisePoolService

    return ExercisePoolService(session, ExerciseGenerationService(AIClient()))


@shared_task(name="ai.translate_word", **_RETRY_KWARGS)
def translate_word(user_id: int, word_uuid: str) -> int:
    """Translate one captured word, so exercises can later be built from cache."""

    async def job(session: AsyncSession) -> int:
        from app.repositories.word import WordRepository
        from app.services.learning.exercise_service import translation_language_for
        from app.services.vocabulary.translation_service import TranslationService

        word = await WordRepository(session).get_one(uuid=UUID(word_uuid))
        if not word:
            return 0
        language = await translation_language_for(session, user_id)
        service = TranslationService(session, _pool_service(session).generator)
        translation = await service.translate_word(word, language)
        if translation:
            logger.info("Translated %r -> %r (%s)", word.lemma, translation, language)
        return int(bool(translation))

    return _run(job)


@shared_task(name="ai.refill_pool", **_RETRY_KWARGS)
def refill_pool(user_id: int, exercise_type: str | None = None) -> int:
    """Top a user's exercise pool back up; returns how many were added."""

    async def job(session: AsyncSession) -> int:
        wanted = ExerciseType(exercise_type) if exercise_type else None
        created = await _pool_service(session).replenish(user_id, wanted)
        logger.info("Refilled pool for user %s: %d exercise(s)", user_id, created)
        return created

    return _run(job)
