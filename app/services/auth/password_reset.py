"""Password reset by emailed link.

Mirrors email verification: issue a single-use, hashed, short-lived token and
email its link; a valid link lets the user set a new password. Requesting a
reset never reveals whether an address exists (no account enumeration), and a
successful reset revokes every existing session.
"""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.security.password import hash_password
from app.database.postgres import get_session
from app.repositories.auth import PasswordResetTokenRepository, RefreshTokenRepository
from app.repositories.user import UserRepository
from app.services.learning.background import schedule_verification_email
from app.services.notifications.templates import password_reset_email

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    # Naive UTC to match the DB's timezone-less DateTime columns.
    return datetime.now(UTC).replace(tzinfo=None)


def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class PasswordResetService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tokens = PasswordResetTokenRepository(session)
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)

    def _reset_url(self, raw_token: str) -> str:
        base = settings.app.BASE_URL.rstrip("/")
        return f"{base}/app/reset.html?token={raw_token}"

    async def request_reset(self, email: str, background: BackgroundTasks) -> None:
        """Email a reset link if the address belongs to an account. Always a
        no-op from the caller's view — the router returns the same 202 either
        way so the response can't be used to probe for registered emails."""
        user = await self.users.get_by_email(email)
        if not user:
            return
        await self.tokens.invalidate_for_user(user.id, _utcnow())
        raw = secrets.token_urlsafe(32)
        await self.tokens.create_one(
            {
                "user_id": user.id,
                "token_hash": _fingerprint(raw),
                "expires_at": _utcnow() + timedelta(hours=settings.email.PASSWORD_RESET_TTL_HOURS),
            }
        )
        subject, html, text = password_reset_email(self._reset_url(raw), user.full_name)
        schedule_verification_email(background, user.email, subject, html, text)

    async def reset(self, raw_token: str, new_password: str) -> bool:
        """Set a new password from a valid token. Returns False for an unknown,
        expired, or already-used token. On success, every session is revoked."""
        stored = await self.tokens.get_by_hash(_fingerprint(raw_token))
        if not stored or stored.used_at is not None or stored.expires_at <= _utcnow():
            return False
        user = await self.users.get_by_id(stored.user_id)
        if not user:
            return False
        await self.tokens.update_one(stored, {"used_at": _utcnow()})
        await self.users.update_one(user, {"hashed_password": hash_password(new_password)})
        # A reset is also the tool for "someone got into my account" — end every
        # existing session so a thief's tokens stop working.
        await self.refresh_tokens.revoke_all_for_user(user.id, _utcnow())
        return True


async def get_password_reset_service(
    session: AsyncSession = Depends(get_session),
) -> PasswordResetService:
    return PasswordResetService(session)
