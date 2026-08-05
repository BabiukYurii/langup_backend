from app.models import Subscription
from app.repositories.base import BaseRepository


class SubscriptionRepository(BaseRepository[Subscription]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=Subscription)

    async def get_for_user(self, user_id: int) -> Subscription | None:
        return await self.get_one(user_id=user_id)

    async def get_by_provider_id(self, provider_subscription_id: str) -> Subscription | None:
        return await self.get_one(provider_subscription_id=provider_subscription_id)
