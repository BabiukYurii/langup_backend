from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.exc import UnauthorizedException
from app.core.security.tokens import create_access_token, create_refresh_token, decode_token
from app.database.postgres import get_session
from app.enums.auth import OAuthProvider, TokenType
from app.repositories.auth import OAuthAccountRepository
from app.repositories.user import UserRepository
from app.schemas.auth import TokenPair
from app.services.auth.oauth_google import GoogleVerifier, get_google_verifier


class AuthService:
    def __init__(self, session: AsyncSession, verifier: GoogleVerifier) -> None:
        self.users = UserRepository(session)
        self.oauth = OAuthAccountRepository(session)
        self.verify_google = verifier

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
        return self._issue_tokens(user.id)

    async def refresh(self, refresh_token: str) -> TokenPair:
        payload = decode_token(refresh_token, settings.jwt.REFRESH_SECRET_KEY, TokenType.REFRESH)
        user = await self.users.get_by_id(int(payload["sub"]))
        if not user:
            raise UnauthorizedException("User not found")
        return self._issue_tokens(user.id)

    @staticmethod
    def _issue_tokens(user_id: int) -> TokenPair:
        return TokenPair(
            access_token=create_access_token(user_id),
            refresh_token=create_refresh_token(user_id),
        )


async def get_auth_service(
    session: AsyncSession = Depends(get_session),
    verifier: GoogleVerifier = Depends(get_google_verifier),
) -> AuthService:
    return AuthService(session, verifier)
