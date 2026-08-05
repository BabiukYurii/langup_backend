from app.models import UsageLimit
from app.repositories.base import BaseRepository


class UsageLimitRepository(BaseRepository[UsageLimit]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=UsageLimit)

    async def get(self, user_id: int, metric: str, period: str) -> UsageLimit | None:
        return await self.get_one(user_id=user_id, metric=metric, period=period)
