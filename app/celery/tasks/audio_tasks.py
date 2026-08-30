"""Warming the audio cache off the request path.

A learner who saves a word will almost certainly tap 🔊 on it, and the first tap
is the only slow one: synthesis takes about a second, everything after is a
cache hit. Doing that second up front, right after the word is captured, means
the button is instant when they actually reach it.

Deliberately best-effort. Nothing here is required for the word to be usable —
if the gateway is busy or storage is down, the clip is simply synthesized later,
on demand. So failures are logged and swallowed rather than retried: a retry
storm over an optional nicety would compete with the exercises the same single
CPU is generating.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.celery.config import celery_app
from app.core import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _session() -> AsyncGenerator[AsyncSession]:
    """A session on an engine of this task's own (see ai_tasks for why)."""
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


async def warm_clips(texts: list[str], language: str, voice: str | None = None) -> int:
    """Synthesize and store each text; returns how many are now cached.

    Shared by the Celery task and the in-process fallback, so both behave the
    same when there is no worker.
    """
    if not settings.audio.AUDIO_ENABLED:
        return 0

    from app.repositories.audio_clip import AudioClipRepository
    from app.services.ai.client import AIClient
    from app.services.audio.service import AudioService
    from app.services.audio.storage import get_audio_storage

    warmed = 0
    async with _session() as session:
        service = AudioService(AudioClipRepository(session), get_audio_storage(), AIClient())
        for text in texts:
            if not text or not text.strip():
                continue
            # A captured sentence may be far longer than the audio cap (2000 vs
            # 400 chars). Skipping it here keeps a predictable case out of the
            # warning log — it is simply not a clip we ever offer.
            if len(text) > settings.audio.AUDIO_MAX_TEXT_LENGTH:
                continue
            try:
                await service.get_or_create(text, language, voice)
                warmed += 1
            except Exception:  # noqa: BLE001 — an optional nicety must never escalate
                logger.warning("Could not warm audio for %r (%s)", text[:40], language, exc_info=True)
    return warmed


@celery_app.task(name="audio.warm_word")
def warm_word_audio(texts: list[str], language: str, voice: str | None = None) -> int:
    """Pre-render the clips a learner is about to ask for."""
    warmed = asyncio.run(warm_clips(texts, language, voice))
    if warmed:
        logger.info("Warmed %d audio clip(s) in %s", warmed, language)
    return warmed
