"""Per-user usage quotas. Free tier is capped per day; an active subscription
lifts the cap. A new day is simply a new counter row, so nothing resets."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.repositories.subscription import SubscriptionRepository
from app.repositories.usage_limit import UsageLimitRepository
from app.services.payments.access import is_active_subscription

# Metric names stored in usage_limits.metric.
METRIC_AI_GENERATIONS = "ai_generations"


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


class UsageLimitService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.usage = UsageLimitRepository(session)
        self.subscriptions = SubscriptionRepository(session)

    async def has_premium(self, user_id: int) -> bool:
        return is_active_subscription(await self.subscriptions.get_for_user(user_id))

    async def generation_budget(self, user_id: int) -> int | None:
        """AI generations the user may still do today. None means unlimited."""
        limit = settings.limits.FREE_DAILY_AI_GENERATIONS
        if limit <= 0 or await self.has_premium(user_id):
            return None
        row = await self.usage.get(user_id, METRIC_AI_GENERATIONS, _today())
        used = row.used if row else 0
        return max(0, limit - used)

    async def consume_generations(self, user_id: int, n: int) -> None:
        """Record `n` generations for today (no-op for premium/disabled limit)."""
        if n <= 0:
            return
        limit = settings.limits.FREE_DAILY_AI_GENERATIONS
        if limit <= 0 or await self.has_premium(user_id):
            return
        period = _today()
        row = await self.usage.get(user_id, METRIC_AI_GENERATIONS, period)
        if row:
            await self.usage.update_one(row, {"used": row.used + n})
        else:
            await self.usage.create_one(
                {"user_id": user_id, "metric": METRIC_AI_GENERATIONS, "period": period, "used": n, "limit": limit}
            )

    async def generation_quota(self, user_id: int) -> dict:
        """Snapshot for the UI: used/limit/remaining and whether unlimited."""
        limit = settings.limits.FREE_DAILY_AI_GENERATIONS
        if limit <= 0 or await self.has_premium(user_id):
            return {"unlimited": True, "used": 0, "limit": None, "remaining": None}
        row = await self.usage.get(user_id, METRIC_AI_GENERATIONS, _today())
        used = row.used if row else 0
        return {"unlimited": False, "used": used, "limit": limit, "remaining": max(0, limit - used)}
