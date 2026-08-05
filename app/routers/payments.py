from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import CurrentUserDep
from app.schemas.payments import (
    CheckoutRequest,
    CheckoutSessionOut,
    PlanOut,
    PortalSessionOut,
    SubscriptionOut,
)
from app.services.payments.billing_service import BillingService, get_billing_service
from app.services.payments.subscription_service import SubscriptionService, get_subscription_service

router = APIRouter(prefix="/payments", tags=["payments"])

BillingServiceDep = Annotated[BillingService, Depends(get_billing_service)]
SubscriptionServiceDep = Annotated[SubscriptionService, Depends(get_subscription_service)]


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(billing: BillingServiceDep) -> list[PlanOut]:
    """Active plans the user can subscribe to."""
    return await billing.list_plans()


@router.post("/checkout", response_model=CheckoutSessionOut)
async def start_checkout(
    data: CheckoutRequest, current_user: CurrentUserDep, billing: BillingServiceDep
) -> CheckoutSessionOut:
    """Open a hosted Stripe Checkout for a plan; returns the URL to redirect to."""
    return await billing.start_checkout(current_user, data.plan_code)


@router.post("/portal", response_model=PortalSessionOut)
async def open_portal(current_user: CurrentUserDep, billing: BillingServiceDep) -> PortalSessionOut:
    """Open Stripe's Customer Portal so the user can manage or cancel."""
    return await billing.start_portal(current_user)


@router.get("/subscription", response_model=SubscriptionOut)
async def my_subscription(current_user: CurrentUserDep, subs: SubscriptionServiceDep) -> SubscriptionOut:
    """The current user's subscription (free tier if none)."""
    return await subs.get_for_user(current_user.id)
