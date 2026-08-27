"""Playlist import on a worker.

Parsing a playlist and analysing up to 50 songs (lyrics fetch + language +
lemmas) is slow and network-bound, so it runs off the request path. Like the
other tasks, each run gets a fresh event loop and its own engine.
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.celery.config import celery_app
from app.core import settings

logger = logging.getLogger(__name__)


@celery_app.task(name="playlist.import", bind=True)
def import_playlist(self, user_id: int, url: str) -> dict:
    """Import a playlist and analyse its songs, reporting per-song progress."""

    def progress(done: int, total: int) -> None:
        self.update_state(state="PROGRESS", meta={"done": done, "total": total})

    async def job() -> dict:
        from app.services.songs.import_service import run_playlist_import

        engine = create_async_engine(settings.db.url, connect_args=settings.db.connect_args, pool_pre_ping=True)
        try:
            async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
                return await run_playlist_import(session, user_id, url, on_progress=progress)
        finally:
            await engine.dispose()

    result = asyncio.run(job())
    logger.info("playlist.import done: %s", result)
    return result
