from app.models import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=User)

    async def get_by_email(self, email: str) -> User | None:
        return await self.get_one(email=email)

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.get_one(id=user_id)
