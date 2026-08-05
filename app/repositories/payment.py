from app.models import Payment
from app.repositories.base import BaseRepository


class PaymentRepository(BaseRepository[Payment]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=Payment)

    async def get_by_provider_id(self, provider_payment_id: str) -> Payment | None:
        return await self.get_one(provider_payment_id=provider_payment_id)
