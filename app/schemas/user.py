from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.enums.user import RoleEnum, UserStatus


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None
    native_language: str | None = None
    target_language: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    native_language: str | None = None
    target_language: str | None = None
    preferences: dict | None = None


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str | None
    role: RoleEnum
    status: UserStatus
    is_email_verified: bool
    native_language: str | None
    target_language: str | None
    preferences: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
