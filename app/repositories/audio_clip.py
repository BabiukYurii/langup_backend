from app.models import AudioClip
from app.repositories.base import BaseRepository


class AudioClipRepository(BaseRepository[AudioClip]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=AudioClip)

    async def get_by_hash(self, hash_: str) -> AudioClip | None:
        return await self.get_one(hash=hash_)
