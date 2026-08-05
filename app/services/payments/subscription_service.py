from datetime import UTC, datetime, timedelta

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.database.postgres import get_session
from app.enums.payments import SubscriptionStatus
from app.repositories.plan import PlanRepository
from app.repositories.subscription import SubscriptionRepository
from app.schemas.payments import SubscriptionOut
from app.services.payments.access import is_active_subscription


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
        return SubscriptionOut(
            status=SubscriptionStatus(sub.status),
            plan_code=plan.code if plan else None,
            is_active=is_active_subscription(sub),
            current_period_end=sub.current_period_end or sub.trial_end_at,
            cancel_at_period_end=sub.cancel_at_period_end,
        )

    async def has_active(self, user_id: int) -> bool:
        return is_active_subscription(await self.subscriptions.get_for_user(user_id))

    async def grant_trial(self, user_id: int) -> None:
        """Give a brand-new account a free Premium trial. No-op if the user
        already has a subscription, trials are disabled, or the plan is missing."""
        days = settings.limits.NEW_USER_TRIAL_DAYS
        if days <= 0:
            return
        if await self.subscriptions.get_for_user(user_id):
            return
        plan = await self.plans.get_by_code(settings.limits.TRIAL_PLAN_CODE)
        if not plan:
            return
        ends = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=days)
        await self.subscriptions.create_one(
            {
                "user_id": user_id,
                "plan_uuid": plan.uuid,
                "status": SubscriptionStatus.TRIALING.value,
                "trial_end_at": ends,
                "current_period_end": ends,
            }
        )


async def get_subscription_service(session: AsyncSession = Depends(get_session)) -> SubscriptionService:
    return SubscriptionService(session)
