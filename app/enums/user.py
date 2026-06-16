from app.enums.base import BaseStrEnum


class RoleEnum(BaseStrEnum):
    USER = "USER"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


class UserStatus(BaseStrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"
