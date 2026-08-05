from sqlalchemy import func, or_, select

from app.models import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=User)

    async def get_by_email(self, email: str) -> User | None:
        return await self.get_one(email=email)

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.get_one(id=user_id)

    async def search(self, page: int = 1, limit: int = 20, query: str | None = None) -> tuple[list[User], int]:
        """Paginated user listing for the admin panel, newest first."""
        offset = (page - 1) * limit
        stmt = select(User)
        count_stmt = select(func.count()).select_from(User)
        if query:
            cond = or_(User.email.ilike(f"%{query}%"), User.full_name.ilike(f"%{query}%"))
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        stmt = stmt.order_by(User.created_at.desc()).offset(offset).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        total = (await self.session.execute(count_stmt)).scalar() or 0
        return list(rows), total
