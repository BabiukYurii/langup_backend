# Role-based access control: require_roles() dependency factory.
from fastapi import Depends

from app.core.exc import ForbiddenException
from app.enums.user import RoleEnum
from app.schemas.user import UserOut
from app.services.auth.dependencies import get_current_user

ADMIN_ROLES = (RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN)


def require_roles(*roles: RoleEnum):
    """Dependency that lets the request through only for the given roles.

    Authentication itself is get_current_user's job — this only checks the
    role on top of it and hands the user through.
    """

    async def _check(current_user: UserOut = Depends(get_current_user)) -> UserOut:
        if current_user.role not in roles:
            raise ForbiddenException("Insufficient role")
        return current_user

    return _check
