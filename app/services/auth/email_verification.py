"""Account email verification.

Issue a single-use token, email its link, and flip `is_email_verified` when the
link is opened. Only the SHA-256 of the token is stored (like refresh tokens):
the token in the link already has full entropy and is looked up by value.
"""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.database.postgres import get_session
from app.models.user import User
from app.repositories.auth import EmailVerificationTokenRepository
from app.repositories.user import UserRepository
from app.services.learning.background import schedule_verification_email
from app.services.notifications.templates import verification_email

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    # Naive UTC to match the DB's timezone-less DateTime columns.
    return datetime.now(UTC).replace(tzinfo=None)


def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class EmailVerificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tokens = EmailVerificationTokenRepository(session)
        self.users = UserRepository(session)

    async def _issue_token(self, user_id: int) -> str:
        """Create a fresh token, retiring any earlier unused ones."""
        await self.tokens.invalidate_for_user(user_id, _utcnow())
        raw = secrets.token_urlsafe(32)
        await self.tokens.create_one(
            {
                "user_id": user_id,
                "token_hash": _fingerprint(raw),
                "expires_at": _utcnow() + timedelta(hours=settings.email.VERIFICATION_TTL_HOURS),
            }
        )
        return raw

    def _verify_url(self, raw_token: str) -> str:
        base = settings.app.BASE_URL.rstrip("/")
        return f"{base}{settings.app.API_PREFIX}/auth/verify-email?token={raw_token}"

    async def send_verification(self, user: User, background: BackgroundTasks) -> bool:
        """Issue a token and dispatch the verification email in the background.
        No-op (returns False) if the account is already verified."""
        if user.is_email_verified:
            return False
        raw = await self._issue_token(user.id)
        subject, html, text = verification_email(self._verify_url(raw), user.full_name)
        schedule_verification_email(background, user.email, subject, html, text)
        return True

    async def verify(self, raw_token: str) -> bool:
        """Consume a token and mark the user verified. Returns False for an
        unknown, expired, or already-used token."""
        stored = await self.tokens.get_by_hash(_fingerprint(raw_token))
        if not stored or stored.used_at is not None or stored.expires_at <= _utcnow():
            return False
        user = await self.users.get_by_id(stored.user_id)
        if not user:
            return False
        await self.tokens.update_one(stored, {"used_at": _utcnow()})
        if not user.is_email_verified:
            await self.users.update_one(user, {"is_email_verified": True})
        return True


async def get_email_verification_service(
    session: AsyncSession = Depends(get_session),
) -> EmailVerificationService:
    return EmailVerificationService(session)
