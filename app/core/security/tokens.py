# JWT encode/decode helpers (python-jose).
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from app.core import settings
from app.core.exc import UnauthorizedException
from app.enums.auth import TokenType


def _encode(subject: str | int, secret: str, expires: timedelta, token_type: TokenType) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject),
        "type": token_type.value,
        "iat": now,
        "exp": now + expires,
    }
    return jwt.encode(payload, secret, algorithm=settings.jwt.ALGORITHM)


def create_access_token(subject: str | int) -> str:
    return _encode(
        subject,
        settings.jwt.ACCESS_SECRET_KEY,
        timedelta(minutes=settings.jwt.ACCESS_EXPIRE_MINUTES),
        TokenType.ACCESS,
    )


def create_refresh_token(subject: str | int) -> str:
    return _encode(
        subject,
        settings.jwt.REFRESH_SECRET_KEY,
        timedelta(days=settings.jwt.REFRESH_EXPIRE_DAYS),
        TokenType.REFRESH,
    )


def decode_token(token: str, secret: str, expected_type: TokenType) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.jwt.ALGORITHM])
    except JWTError:
        raise UnauthorizedException("Invalid or expired token")
    if payload.get("type") != expected_type.value:
        raise UnauthorizedException("Invalid token type")
    return payload
