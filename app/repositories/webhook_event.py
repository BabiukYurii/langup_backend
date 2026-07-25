from app.models import WebhookEvent
from app.repositories.base import BaseRepository


class WebhookEventRepository(BaseRepository[WebhookEvent]):
    def __init__(self, session) -> None:
        super().__init__(session=session, model=WebhookEvent)

    async def get_by_event(self, provider: str, event_id: str) -> WebhookEvent | None:
        return await self.get_one(provider=provider, event_id=event_id)
