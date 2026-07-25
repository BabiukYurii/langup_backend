from app.models import Plan
from app.repositories.base import BaseRepository


class PlanRepository(BaseRepository[Plan]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=Plan)

    async def get_by_code(self, code: str) -> Plan | None:
        return await self.get_one(code=code)

    async def list_active(self) -> list[Plan]:
        rows, _ = await self.get_many(limit=100, is_active=True)
        return rows
