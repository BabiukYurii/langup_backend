"""Collect audio nothing can reach any more.

Two kinds of dead weight, both left behind when the cache key changes —
bumping CACHE_VERSION, switching AUDIO_FORMAT, editing a phrase that was
already warmed, changing a language's default voice:

  STALE ROWS  the row and its blob still agree, but the hash the app now
              computes for that text no longer matches the stored one, so
              nothing will ever look it up. Invisible to an orphan check,
              because the row does still point at its object.

  ORPHANS     a blob no row points at. Removing a stale row turns its blob
              into one of these, so the two passes run in that order.

Reports by default and deletes nothing. Pass --delete to actually remove them:

    docker exec -w /app -e PYTHONPATH=/app langup-api python scripts/sweep_audio_orphans.py
    docker exec -w /app -e PYTHONPATH=/app langup-api python scripts/sweep_audio_orphans.py --delete

Deleting is safe in the sense that nothing is lost for good — every clip can be
re-synthesized from the text in its row — but a blob written seconds ago whose
row has not committed yet would look orphaned, so avoid running --delete while
a warm-up is in flight.
"""

import asyncio
import sys

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import settings
from app.repositories.audio_clip import AudioClipRepository
from app.services.ai.client import AIClient
from app.services.audio.service import AudioService
from app.services.audio.storage import get_audio_storage


async def main(delete: bool) -> int:
    engine = create_async_engine(settings.db.url, connect_args=settings.db.connect_args, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            service = AudioService(AudioClipRepository(session), get_audio_storage(), AIClient())
            orphans, removed = await service.sweep_orphans(delete=delete)
    finally:
        await engine.dispose()

    if not orphans:
        print("no orphaned audio objects")
        return 0

    for key in orphans[:20]:
        print(f"  {key}")
    if len(orphans) > 20:
        print(f"  ... and {len(orphans) - 20} more")

    if delete:
        print(f"\ndeleted {removed} of {len(orphans)} orphaned object(s)")
    else:
        print(f"\n{len(orphans)} orphaned object(s); re-run with --delete to remove them")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(delete="--delete" in sys.argv)))
