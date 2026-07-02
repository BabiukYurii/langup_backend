from app.models import Source
from app.repositories.base import BaseRepository


class SourceRepository(BaseRepository[Source]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=Source)

    async def get_by_user_url(self, user_id: int, url: str) -> Source | None:
        return await self.get_one(user_id=user_id, url=url)
