from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.security.rbac import ADMIN_ROLES, require_roles
from app.schemas.admin import AdminExerciseOut, AdminUserUpdate
from app.schemas.capture import UserWordOut
from app.schemas.pagination import Page
from app.schemas.user import UserOut
from app.services.admin_service import AdminService, get_admin_service

router = APIRouter(prefix="/admin", tags=["admin"])

AdminUserDep = Annotated[UserOut, Depends(require_roles(*ADMIN_ROLES))]
AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]


@router.get("/users", response_model=Page[UserOut])
async def list_users(
    admin: AdminUserDep,
    service: AdminServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    query: str | None = Query(None, max_length=128),
) -> Page[UserOut]:
    """All users, newest first; `query` matches email or name."""
    return await service.list_users(page=page, limit=limit, query=query)


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: int, admin: AdminUserDep, service: AdminServiceDep) -> UserOut:
    return await service.get_user(user_id)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: int, data: AdminUserUpdate, admin: AdminUserDep, service: AdminServiceDep) -> UserOut:
    """Change a user's role or status (suspend/restore)."""
    return await service.update_user(admin, user_id, data)


@router.get("/users/{user_id}/vocabulary", response_model=Page[UserWordOut])
async def user_vocabulary(
    user_id: int,
    admin: AdminUserDep,
    service: AdminServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> Page[UserWordOut]:
    return await service.user_vocabulary(user_id, page=page, limit=limit)


@router.get("/users/{user_id}/exercises", response_model=Page[AdminExerciseOut])
async def user_exercises(
    user_id: int,
    admin: AdminUserDep,
    service: AdminServiceDep,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> Page[AdminExerciseOut]:
    return await service.user_exercises(user_id, page=page, limit=limit)
