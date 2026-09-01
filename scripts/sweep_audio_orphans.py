"""Collect audio nothing can reach any more.

Two kinds of dead weight, both left behind when the cache key changes —
bumping CACHE_VERSION, switching AUDIO_FORMAT, editing a phrase that was
already warmed, changing a language's default voice:

  STALE ROWS  the row and its blob still agree, but the hash the app now
              computes for that text no longer matches the stored one, so
              nothing will ever look it up. Invisible to an orphan check,
              because the row does still point at its object.

  UNUSED      a clip in a (language, voice) nobody would be served any more,
              left behind when someone changed voice. Only swept when NO user
              still uses that voice — the cache is shared, so one learner
              switching says nothing about the rest. The picker's demo phrases
              are spared: every voice is auditionable by anyone.

  ORPHANS     a blob no row points at. Removing a row of either kind above
              turns its blob into one of these, so the passes run in that
              order.

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
from app.services.audio.demos import demo_texts
from app.services.audio.service import AudioService
from app.services.audio.storage import get_audio_storage
from app.services.audio.usage import voices_in_use


def report(what: str, items: list[str], removed: int, delete: bool) -> None:
    if not items:
        return
    print(f"{len(items)} {what}:")
    for item in items[:10]:
        print(f"  {item}")
    if len(items) > 10:
        print(f"  ... and {len(items) - 10} more")
    print(f"  -> deleted {removed}" if delete else "  -> re-run with --delete to remove")


async def main(delete: bool) -> int:
    engine = create_async_engine(settings.db.url, connect_args=settings.db.connect_args, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            service = AudioService(AudioClipRepository(session), get_audio_storage(), AIClient())
            # Row passes first: dropping a row turns its blob into an orphan,
            # which the last pass then collects in the same run.
            stale, stale_removed = await service.sweep_stale(delete=delete)
            unused, unused_removed = await service.sweep_unused_voices(
                await voices_in_use(session), demo_texts(), delete=delete
            )
            orphans, orphans_removed = await service.sweep_orphans(delete=delete)
    finally:
        await engine.dispose()

    report("unreachable clip(s)", stale, stale_removed, delete)
    report("clip(s) in voices nobody uses", unused, unused_removed, delete)
    report("orphaned object(s)", orphans, orphans_removed, delete)
    if not stale and not unused and not orphans:
        print("nothing to collect")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(delete="--delete" in sys.argv)))
