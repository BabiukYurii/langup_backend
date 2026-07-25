from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.exc import BadRequestException, ObjectNotFoundException
from app.database.postgres import get_session
from app.enums.payments import PaymentProvider
from app.repositories.plan import PlanRepository
from app.schemas.payments import CheckoutSessionOut, PlanOut
from app.schemas.user import UserOut
from app.services.payments.providers.stripe_provider import StripeProvider


class BillingService:
    """Opens a hosted checkout for a plan. Provider-agnostic at the call site;
    Stripe is the only wired provider for now."""

    def __init__(self, session: AsyncSession) -> None:
        self.plans = PlanRepository(session)

    async def list_plans(self) -> list[PlanOut]:
        return [PlanOut.model_validate(p) for p in await self.plans.list_active()]

    async def start_checkout(self, user: UserOut, plan_code: str) -> CheckoutSessionOut:
        cfg = settings.payments
        if not cfg.stripe_enabled:
            raise BadRequestException("Payments are not configured")

        plan = await self.plans.get_by_code(plan_code)
        if not plan or not plan.is_active:
            raise ObjectNotFoundException(plan_code, "Plan")
        price_id = (plan.provider_price_ids or {}).get(PaymentProvider.STRIPE.value)
        if not price_id:
            raise BadRequestException(f"Plan {plan_code!r} has no Stripe price configured")

        provider = StripeProvider(cfg.STRIPE_API_KEY, cfg.STRIPE_WEBHOOK_SECRET)
        base = settings.app.BASE_URL.rstrip("/")
        session = await provider.create_checkout_session(
            price_id=price_id,
            customer_email=user.email,
            success_url=base + cfg.SUCCESS_PATH,
            cancel_url=base + cfg.CANCEL_PATH,
            client_reference_id=str(user.id),
            # Echoed back on the webhook so we know which plan was bought.
            metadata={"user_id": str(user.id), "plan_uuid": str(plan.uuid)},
        )
        return CheckoutSessionOut(checkout_url=session.url)


async def get_billing_service(session: AsyncSession = Depends(get_session)) -> BillingService:
    return BillingService(session)
