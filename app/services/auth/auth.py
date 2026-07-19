import hashlib
import logging
from datetime import UTC, datetime, timedelta

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.exc import ObjectAlreadyExistsException, UnauthorizedException
from app.core.security.password import hash_password, verify_password
from app.core.security.tokens import create_access_token, create_refresh_token, decode_token
from app.database.postgres import get_session
from app.enums.auth import OAuthProvider, TokenType
from app.repositories.auth import OAuthAccountRepository, RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenPair
from app.services.auth.oauth_google import GoogleVerifier, get_google_verifier

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    # Naive UTC to match the DB's timezone-less DateTime columns.
    return datetime.now(UTC).replace(tzinfo=None)


def _fingerprint(token: str) -> str:
    """What we store instead of the token itself.

    A plain SHA-256 is right here, unlike for passwords: the token already has
    full entropy, and we must look it up by value on every refresh.
    """
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, session: AsyncSession, verifier: GoogleVerifier) -> None:
        self.users = UserRepository(session)
        self.oauth = OAuthAccountRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.verify_google = verifier

    async def register(self, data: RegisterRequest) -> TokenPair:
        """Create a password-based account and sign the user in."""
        if await self.users.get_by_email(data.email):
            raise ObjectAlreadyExistsException(data.email, "User")
        user = await self.users.create_one(
            {
                "email": data.email,
                "hashed_password": hash_password(data.password),
                "full_name": data.full_name,
            }
        )
        return await self._issue_tokens(user.id)

    async def login(self, data: LoginRequest) -> TokenPair:
        """Password sign-in. One generic 401 for unknown email, OAuth-only
        accounts, and wrong password — no account enumeration."""
        user = await self.users.get_by_email(data.email)
        if not user or not user.hashed_password or not verify_password(data.password, user.hashed_password):
            raise UnauthorizedException("Invalid email or password")
        return await self._issue_tokens(user.id)

    async def google_login(self, id_token: str) -> TokenPair:
        """Sign in or sign up a user from a verified Google ID token."""
        info = self.verify_google(id_token)
        email = info.get("email")
        google_sub = info.get("sub")
        if not email or not google_sub:
            raise UnauthorizedException("Google token is missing email or subject")

        account = await self.oauth.get_by_provider_account(OAuthProvider.GOOGLE.value, google_sub)
        if account:
            user = await self.users.get_by_id(account.user_id)
        else:
            user = await self.users.get_by_email(email)
            if not user:  # first time we see this person -> create the account
                user = await self.users.create_one(
                    {
                        "email": email,
                        "full_name": info.get("name"),
                        "is_email_verified": bool(info.get("email_verified", False)),
                    }
                )
            await self.oauth.create_one(
                {
                    "user_id": user.id,
                    "provider": OAuthProvider.GOOGLE.value,
                    "provider_account_id": google_sub,
                    "email": email,
                }
            )

        if not user:
            raise UnauthorizedException("Linked user no longer exists")
        return await self._issue_tokens(user.id)

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Exchange a refresh token for a new pair, retiring the old one.

        A valid signature is not enough: the token must still be live in the
        database, which is what makes logout and revocation real.
        """
        payload = decode_token(refresh_token, settings.jwt.REFRESH_SECRET_KEY, TokenType.REFRESH)
        stored = await self.refresh_tokens.get_by_hash(_fingerprint(refresh_token))
        if not stored:
            raise UnauthorizedException("Refresh token is not recognised")

        if stored.revoked_at is not None:
            # Only rotation sets replaced_by. A token retired by logout or by
            # theft detection has none, and must be dead the instant it is —
            # no window where signing out still leaves a way back in.
            grace = timedelta(seconds=settings.auth.REFRESH_REUSE_GRACE_SECONDS)
            rotated = stored.replaced_by is not None
            if not rotated or _utcnow() - stored.revoked_at > grace:
                # Long after rotation this is a replay: the token leaked, and
                # which copy is the thief's is unknowable — so end every session
                # of that user rather than guess.
                logger.warning("Reuse of a revoked refresh token for user %s", stored.user_id)
                await self.refresh_tokens.revoke_all_for_user(stored.user_id, _utcnow())
                raise UnauthorizedException("Refresh token has been revoked")
            # Within the window it is two of the user's own clients refreshing
            # at the same moment, which must not log them out.
            logger.info("Concurrent refresh for user %s, inside the grace window", stored.user_id)

        if stored.expires_at <= _utcnow():
            raise UnauthorizedException("Refresh token has expired")

        user = await self.users.get_by_id(int(payload["sub"]))
        if not user:
            raise UnauthorizedException("User not found")

        tokens = await self._issue_tokens(user.id)
        issued = await self.refresh_tokens.get_by_hash(_fingerprint(tokens.refresh_token))
        await self.refresh_tokens.update_one(
            stored, {"revoked_at": _utcnow(), "replaced_by": issued.uuid if issued else None}
        )
        return tokens

    async def logout(self, refresh_token: str) -> None:
        """Retire one session. Unknown or already-dead tokens pass quietly:
        the caller wanted them gone, and they are."""
        stored = await self.refresh_tokens.get_by_hash(_fingerprint(refresh_token))
        if stored and stored.revoked_at is None:
            await self.refresh_tokens.update_one(stored, {"revoked_at": _utcnow()})

    async def logout_everywhere(self, user_id: int) -> int:
        """Retire every session of a user; returns how many were live."""
        return await self.refresh_tokens.revoke_all_for_user(user_id, _utcnow())

    async def _issue_tokens(self, user_id: int) -> TokenPair:
        refresh_token = create_refresh_token(user_id)
        await self.refresh_tokens.create_one(
            {
                "user_id": user_id,
                "token_hash": _fingerprint(refresh_token),
                "expires_at": _utcnow() + timedelta(days=settings.jwt.REFRESH_EXPIRE_DAYS),
            }
        )
        return TokenPair(access_token=create_access_token(user_id), refresh_token=refresh_token)


async def get_auth_service(
    session: AsyncSession = Depends(get_session),
    verifier: GoogleVerifier = Depends(get_google_verifier),
) -> AuthService:
    return AuthService(session, verifier)
