from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.exc import UnauthorizedException
from app.core.security.tokens import decode_token
from app.database.postgres import get_session
from app.enums.auth import TokenType
from app.repositories.user import UserRepository
from app.schemas.user import UserOut

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    if credentials is None:
        raise UnauthorizedException("Missing bearer token")
    payload = decode_token(credentials.credentials, settings.jwt.ACCESS_SECRET_KEY, TokenType.ACCESS)
    user = await UserRepository(session).get_by_id(int(payload["sub"]))
    if not user:
        raise UnauthorizedException("User not found")
    return UserOut.model_validate(user)
