"""Delete audio blobs that no database row points at any more.

Orphans appear whenever a clip's cache key changes but its blob does not go
with it: bumping CACHE_VERSION, editing a demo phrase that was already warmed,
changing the voice a language defaults to. The old object stays in storage
forever and nothing will ever ask for it again.

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
