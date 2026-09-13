"""AI jobs that must not run inside a web request.

Generation is CPU-bound and slow, and Ollama serves one inference at a time, so
these run on a worker with a single concurrent slot. Failures retry: the model
is not deterministic, and a word it refused once usually works on a second try.

Tasks bind to our Celery app explicitly rather than via @shared_task: the web
process never loads the worker's entry point, so "the current app" there is
Celery's default one — pointing at an amqp broker that does not exist.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.celery.config import celery_app
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
async def _session() -> AsyncGenerator[AsyncSession]:
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


@celery_app.task(name="ai.translate_word", **_RETRY_KWARGS)
def translate_word(user_id: int, word_uuid: str) -> int:
    """Translate one captured word, so exercises can later be built from cache."""

    async def job(session: AsyncSession) -> int:
        from app.repositories.word import WordRepository
        from app.services.learning.exercise_service import translation_language_for
        from app.services.learning.model_busy import mark_user_work
        from app.services.vocabulary.translation_service import TranslationService

        # A learner is waiting at the end of this: hold the warmer off.
        await mark_user_work()
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


@celery_app.task(name="ai.generate_word_exercises", **_RETRY_KWARGS)
def generate_word_exercises(user_id: int, user_word_uuid: str) -> int:
    """Build the full exercise set for one newly saved word."""

    async def job(session: AsyncSession) -> int:
        from app.services.learning.model_busy import mark_user_work

        # A learner is going to practise this word shortly: claim the model so
        # the playlist warmer stands aside.
        await mark_user_work()
        created = await _pool_service(session).generate_for_word(user_id, UUID(user_word_uuid))
        logger.info("Built %d exercise(s) for user word %s", created, user_word_uuid)
        return created

    return _run(job)


@celery_app.task(name="ai.backfill_exercises")
def backfill_exercises(user_id: int | None = None) -> int:
    """Catch up words that never got their full set of exercises.

    Generation happens once, at capture. A word saved while the daily
    allowance was spent, or while the gateway was down, is never revisited —
    so this is the only thing that goes back for it. Called by beat with no
    argument (every account), or with one to catch a single account up now.

    Not retried on failure: it runs again on the next tick anyway, and the
    words it did not reach are exactly the ones it will find next time.
    """

    async def job(session: AsyncSession) -> int:
        from sqlalchemy import distinct, select

        from app.models import UserWord
        from app.services.learning.model_busy import model_is_busy

        service = _pool_service(session)
        if user_id is not None:
            # Asked for explicitly, so the schedule's on/off switch does not
            # apply — somebody is waiting for this account to catch up.
            return await service.backfill_missing(user_id)
        if not settings.exercises.EXERCISE_BACKFILL_ENABLED:
            return 0

        total = 0
        for uid in (await session.execute(select(distinct(UserWord.user_id)))).scalars().all():
            if await model_is_busy():
                break  # a learner is mid-request; the rest keeps until next tick
            total += await service.backfill_missing(uid)
        if total:
            logger.info("Backfilled %d exercise(s)", total)
        return total

    return _run(job)


@celery_app.task(name="ai.refill_pool", **_RETRY_KWARGS)
def refill_pool(user_id: int, exercise_type: str | None = None, language: str | None = None) -> int:
    """Top a user's exercise pool back up; returns how many were added."""

    async def job(session: AsyncSession) -> int:
        from app.services.learning.model_busy import mark_user_work

        # Several inferences back to back — precisely what warming must not
        # queue behind, and must not get in front of.
        await mark_user_work()
        wanted = ExerciseType(exercise_type) if exercise_type else None
        created = await _pool_service(session).replenish(user_id, wanted, language)
        logger.info("Refilled pool for user %s: %d exercise(s)", user_id, created)
        return created

    return _run(job)
