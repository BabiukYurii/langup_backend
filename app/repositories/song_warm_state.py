from datetime import UTC, datetime
from uuid import UUID

from app.models import SongWarmState
from app.repositories.base import BaseRepository


class SongWarmStateRepository(BaseRepository[SongWarmState]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=SongWarmState)

    async def get_or_create(self, song_uuid: UUID, target_language: str) -> SongWarmState:
        key = {"song_uuid": song_uuid, "target_language": target_language.lower()}
        existing = await self.get_one(**key)
        return existing or await self.create_one(key)

    async def mark_attempted(self, song_uuid: UUID, target_language: str) -> SongWarmState:
        """Stamp a pair as picked, before any work is done.

        Written up front on purpose: a run that dies mid-song must still move
        the rotation on, or one unwarmable song would be chosen forever.
        """
        state = await self.get_or_create(song_uuid, target_language)
        return await self.update_one(state, {"attempted_at": datetime.now(UTC).replace(tzinfo=None)})

    async def mark_completed(self, song_uuid: UUID, target_language: str, words_warmed: int = 0) -> SongWarmState:
        """Stamp a pair as fully warmed, so it stops being fetched."""
        state = await self.get_or_create(song_uuid, target_language)
        now = datetime.now(UTC).replace(tzinfo=None)
        return await self.update_one(
            state,
            {
                "attempted_at": now,
                "completed_at": now,
                "words_warmed": (state.words_warmed or 0) + words_warmed,
            },
        )
