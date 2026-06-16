from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exc import ObjectAlreadyExistsException, ObjectNotFoundException
from app.core.security.password import hash_password
from app.database.postgres import get_session
from app.models import User
from app.repositories.user import UserRepository
from app.schemas.pagination import Page
from app.schemas.user import UserCreate, UserOut, UserUpdate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = UserRepository(session)

    async def create_user(self, data: UserCreate) -> UserOut:
        if await self.repository.get_by_email(data.email):
            raise ObjectAlreadyExistsException(data.email, "User")

        payload = {
            "email": data.email,
            "hashed_password": hash_password(data.password),
            "full_name": data.full_name,
            "native_language": data.native_language,
            "target_language": data.target_language,
        }
        user = await self.repository.create_one(payload)
        return UserOut.model_validate(user)

    async def get_user(self, user_id: int) -> UserOut:
        user = await self._get_or_404(user_id)
        return UserOut.model_validate(user)

    async def list_users(self, page: int = 1, limit: int = 20) -> Page[UserOut]:
        users, total = await self.repository.get_many(page=page, limit=limit, order_by=[User.id])
        return Page[UserOut](
            items=[UserOut.model_validate(u) for u in users],
            total=total,
            page=page,
            limit=limit,
        )

    async def update_user(self, user_id: int, data: UserUpdate) -> UserOut:
        user = await self._get_or_404(user_id)
        changes = data.model_dump(exclude_unset=True)
        updated = await self.repository.update_one(user, changes)
        return UserOut.model_validate(updated)

    async def delete_user(self, user_id: int) -> None:
        await self._get_or_404(user_id)
        # Delete via a single statement; child rows are removed by the DB-level
        # ON DELETE CASCADE foreign keys (no ORM relationship traversal needed).
        await self.repository.delete_by(id=user_id)

    async def _get_or_404(self, user_id: int) -> User:
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise ObjectNotFoundException(user_id, "User")
        return user


async def get_user_service(session: AsyncSession = Depends(get_session)) -> UserService:
    return UserService(session)
