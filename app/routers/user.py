from fastapi import APIRouter, status

from app.dependencies import UserServiceDep
from app.schemas.pagination import Page
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, user_service: UserServiceDep) -> UserOut:
    return await user_service.create_user(data)


@router.get("", response_model=Page[UserOut])
async def list_users(user_service: UserServiceDep, page: int = 1, limit: int = 20) -> Page[UserOut]:
    return await user_service.list_users(page=page, limit=limit)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, user_service: UserServiceDep) -> UserOut:
    return await user_service.get_user(user_id)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(user_id: int, data: UserUpdate, user_service: UserServiceDep) -> UserOut:
    return await user_service.update_user(user_id, data)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, user_service: UserServiceDep) -> None:
    await user_service.delete_user(user_id)
