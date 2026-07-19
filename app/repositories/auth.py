from datetime import datetime

from sqlalchemy import update

from app.models import OAuthAccount, RefreshToken
from app.repositories.base import BaseRepository


class OAuthAccountRepository(BaseRepository[OAuthAccount]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=OAuthAccount)

    async def get_by_provider_account(self, provider: str, provider_account_id: str) -> OAuthAccount | None:
        return await self.get_one(provider=provider, provider_account_id=provider_account_id)


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=RefreshToken)

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return await self.get_one(token_hash=token_hash)

    async def revoke_all_for_user(self, user_id: int, now: datetime) -> int:
        """Kill every live token of one user — used on logout-everywhere and
        when a revoked token reappears, which means one of them leaked."""
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount or 0
