from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.exc import ForbiddenException
from app.core.security.rbac import ADMIN_ROLES, require_roles
from app.dependencies import CurrentUserDep, UserServiceDep
from app.schemas.pagination import Page
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])

AdminOnly = Annotated[UserOut, Depends(require_roles(*ADMIN_ROLES))]


def _ensure_self_or_admin(current_user: UserOut, user_id: int) -> None:
    """A user may only read or change their own account; admins, anyone's."""
    if current_user.id != user_id and current_user.role not in ADMIN_ROLES:
        raise ForbiddenException("You can only manage your own account")


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, user_service: UserServiceDep) -> UserOut:
    """Open registration (also available via /auth/register)."""
    return await user_service.create_user(data)


@router.get("", response_model=Page[UserOut])
async def list_users(admin: AdminOnly, user_service: UserServiceDep, page: int = 1, limit: int = 20) -> Page[UserOut]:
    """The full user directory — admins only."""
    return await user_service.list_users(page=page, limit=limit)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, current_user: CurrentUserDep, user_service: UserServiceDep) -> UserOut:
    _ensure_self_or_admin(current_user, user_id)
    return await user_service.get_user(user_id)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int, data: UserUpdate, current_user: CurrentUserDep, user_service: UserServiceDep
) -> UserOut:
    _ensure_self_or_admin(current_user, user_id)
    return await user_service.update_user(user_id, data)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, current_user: CurrentUserDep, user_service: UserServiceDep) -> None:
    _ensure_self_or_admin(current_user, user_id)
    await user_service.delete_user(user_id)
