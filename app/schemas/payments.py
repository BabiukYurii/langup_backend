from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.enums.payments import BillingInterval, PlanTier, SubscriptionStatus


class PlanOut(BaseModel):
    uuid: UUID
    code: str
    tier: PlanTier
    interval: BillingInterval | None
    price_cents: int
    currency: str
    trial_days: int

    model_config = ConfigDict(from_attributes=True)


class CheckoutRequest(BaseModel):
    plan_code: str


class CheckoutSessionOut(BaseModel):
    # The hosted Stripe Checkout URL to redirect the browser to.
    checkout_url: str


class PortalSessionOut(BaseModel):
    # The hosted Stripe Customer Portal URL (manage / cancel).
    portal_url: str


class SubscriptionOut(BaseModel):
    status: SubscriptionStatus
    plan_code: str | None = None
    is_active: bool
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
