from sqlalchemy import select

from app.models import AudioClip
from app.repositories.base import BaseRepository


class AudioClipRepository(BaseRepository[AudioClip]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=AudioClip)

    async def get_by_hash(self, hash_: str) -> AudioClip | None:
        return await self.get_one(hash=hash_)

    async def all_object_keys(self) -> set[str]:
        """Every object key the database still points at.

        A set, and only that column: the orphan sweep compares it against what
        storage holds, and pulling whole rows for that would load the text of
        every clip for nothing.
        """
        result = await self.session.execute(select(AudioClip.object_key))
        return set(result.scalars().all())
