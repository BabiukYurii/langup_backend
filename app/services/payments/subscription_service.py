from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres import get_session
from app.enums.payments import ACTIVE_SUBSCRIPTION_STATUSES, SubscriptionStatus
from app.repositories.plan import PlanRepository
from app.repositories.subscription import SubscriptionRepository
from app.schemas.payments import SubscriptionOut


class SubscriptionService:
    """Reads a user's subscription and answers the one question the rest of the
    app cares about: does this user have paid access right now."""

    def __init__(self, session) -> None:
        self.subscriptions = SubscriptionRepository(session)
        self.plans = PlanRepository(session)

    async def get_for_user(self, user_id: int) -> SubscriptionOut:
        sub = await self.subscriptions.get_for_user(user_id)
        if not sub:
            # Everyone without a row is implicitly on the free tier.
            return SubscriptionOut(status=SubscriptionStatus.EXPIRED, is_active=False)
        plan = await self.plans.get_one(uuid=sub.plan_uuid)
        status = SubscriptionStatus(sub.status)
        return SubscriptionOut(
            status=status,
            plan_code=plan.code if plan else None,
            is_active=status in ACTIVE_SUBSCRIPTION_STATUSES,
            current_period_end=sub.current_period_end,
            cancel_at_period_end=sub.cancel_at_period_end,
        )

    async def has_active(self, user_id: int) -> bool:
        sub = await self.subscriptions.get_for_user(user_id)
        return bool(sub and SubscriptionStatus(sub.status) in ACTIVE_SUBSCRIPTION_STATUSES)


async def get_subscription_service(session: AsyncSession = Depends(get_session)) -> SubscriptionService:
    return SubscriptionService(session)
