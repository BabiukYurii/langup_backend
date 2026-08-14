"""Bulk dictionary import on a worker.

An import can be thousands of rows; running it on the worker keeps it off the
request path and lets it survive a restart. Like ai_tasks, each run gets a
fresh event loop and its own engine (an async engine can't cross loops).
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.celery.config import celery_app
from app.core import settings

logger = logging.getLogger(__name__)


@celery_app.task(name="dictionary.import", bind=True)
def import_dictionary(self, source_language: str, target_language: str, pairs: list) -> dict:
    """Upsert a batch of (word, translation) pairs into the shared dictionary."""

    def progress(done: int, total: int) -> None:
        self.update_state(state="PROGRESS", meta={"done": done, "total": total})

    async def job() -> dict:
        from app.schemas.dictionary import DictionaryEntry
        from app.services.vocabulary.dictionary_service import DictionaryImportService

        engine = create_async_engine(settings.db.url, connect_args=settings.db.connect_args, pool_pre_ping=True)
        try:
            async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
                entries = [DictionaryEntry(word=w, translation=t) for w, t in pairs]
                return await DictionaryImportService(session).import_entries(
                    source_language, target_language, entries, on_progress=progress
                )
        finally:
            await engine.dispose()

    result = asyncio.run(job())
    logger.info("dictionary.import done: %s", result)
    return result


@celery_app.task(name="dictionary.normalize_import", bind=True)
def normalize_import_dictionary(self, source_language: str, target_language: str, raw_text: str) -> dict:
    """LLM-normalize messy raw text into pairs, then upsert them."""

    def progress(done: int, total: int) -> None:
        # The LLM phase is the slow one, so its chunk progress is what we report.
        self.update_state(state="PROGRESS", meta={"done": done, "total": total})

    async def job() -> dict:
        from app.services.ai.client import AIClient
        from app.services.vocabulary.dictionary_service import DictionaryImportService

        engine = create_async_engine(settings.db.url, connect_args=settings.db.connect_args, pool_pre_ping=True)
        try:
            async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
                service = DictionaryImportService(session)
                entries = await service.normalize_via_llm(
                    source_language, target_language, raw_text, AIClient(), on_progress=progress
                )
                if not entries:
                    return {"created": 0, "updated": 0}
                return await service.import_entries(source_language, target_language, entries)
        finally:
            await engine.dispose()

    result = asyncio.run(job())
    logger.info("dictionary.normalize_import done: %s", result)
    return result
