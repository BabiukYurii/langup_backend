from app.models import OAuthAccount
from app.repositories.base import BaseRepository


class OAuthAccountRepository(BaseRepository[OAuthAccount]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=OAuthAccount)

    async def get_by_provider_account(self, provider: str, provider_account_id: str) -> OAuthAccount | None:
        return await self.get_one(provider=provider, provider_account_id=provider_account_id)
