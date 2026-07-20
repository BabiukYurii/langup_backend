from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exc import BadRequestException, ForbiddenException, ObjectNotFoundException
from app.database.postgres import get_session
from app.enums.user import RoleEnum
from app.models import Exercise
from app.repositories.exercise import ExerciseRepository
from app.repositories.user import UserRepository
from app.repositories.user_word import UserWordRepository
from app.schemas.admin import AdminExerciseOut, AdminUserUpdate
from app.schemas.capture import UserWordOut
from app.schemas.pagination import Page
from app.schemas.user import UserOut


class AdminService:
    """Moderation over users and their learning data.

    Read-mostly: the only writes are role/status changes, with guardrails so
    an admin can't silently lock themselves (or a higher role) out.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)
        self.user_words = UserWordRepository(session)
        self.exercises = ExerciseRepository(session)

    async def list_users(self, page: int = 1, limit: int = 20, query: str | None = None) -> Page[UserOut]:
        rows, total = await self.users.search(page=page, limit=limit, query=query)
        return Page[UserOut](items=[UserOut.model_validate(u) for u in rows], total=total, page=page, limit=limit)

    async def get_user(self, user_id: int) -> UserOut:
        user = await self.users.get_by_id(user_id)
        if not user:
            raise ObjectNotFoundException(user_id, "User")
        return UserOut.model_validate(user)

    async def update_user(self, acting: UserOut, user_id: int, data: AdminUserUpdate) -> UserOut:
        user = await self.users.get_by_id(user_id)
        if not user:
            raise ObjectNotFoundException(user_id, "User")
        # Guardrails: nobody edits themselves here (no self-demotion/suspension
        # by accident), and only a SUPER_ADMIN may touch another privileged user.
        if user.id == acting.id:
            raise BadRequestException("Use your own profile settings, not the admin panel")
        if user.role != RoleEnum.USER.value and acting.role != RoleEnum.SUPER_ADMIN:
            raise ForbiddenException("Only a SUPER_ADMIN can manage privileged users")
        if data.role == RoleEnum.SUPER_ADMIN and acting.role != RoleEnum.SUPER_ADMIN:
            raise ForbiddenException("Only a SUPER_ADMIN can grant SUPER_ADMIN")

        changes = {k: v.value for k, v in data.model_dump(exclude_none=True).items()}
        if changes:
            user = await self.users.update_one(user, changes)
        return UserOut.model_validate(user)

    async def user_vocabulary(self, user_id: int, page: int = 1, limit: int = 20) -> Page[UserWordOut]:
        await self.get_user(user_id)  # 404 early on a bad id
        rows, total = await self.user_words.list_for_user(user_id, page=page, limit=limit)
        return Page[UserWordOut](
            items=[UserWordOut.from_user_word(uw) for uw in rows], total=total, page=page, limit=limit
        )

    async def user_exercises(self, user_id: int, page: int = 1, limit: int = 20) -> Page[AdminExerciseOut]:
        await self.get_user(user_id)
        rows, total = await self.exercises.get_many(
            page=page, limit=limit, order_by=[Exercise.created_at.desc()], user_id=user_id
        )
        return Page[AdminExerciseOut](
            items=[AdminExerciseOut.model_validate(e) for e in rows], total=total, page=page, limit=limit
        )


async def get_admin_service(session: AsyncSession = Depends(get_session)) -> AdminService:
    return AdminService(session)
