import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.database.postgres import get_session
from app.enums.payments import PaymentProvider, PaymentStatus, SubscriptionStatus
from app.repositories.payment import PaymentRepository
from app.repositories.subscription import SubscriptionRepository
from app.repositories.webhook_event import WebhookEventRepository
from app.services.payments.providers.stripe_provider import StripeProvider

logger = logging.getLogger(__name__)

# Stripe subscription status -> ours.
_STRIPE_STATUS = {
    "trialing": SubscriptionStatus.TRIALING,
    "active": SubscriptionStatus.ACTIVE,
    "past_due": SubscriptionStatus.PAST_DUE,
    "unpaid": SubscriptionStatus.PAST_DUE,
    "canceled": SubscriptionStatus.CANCELED,
    "incomplete": SubscriptionStatus.EXPIRED,
    "incomplete_expired": SubscriptionStatus.EXPIRED,
}


def _ts(value) -> datetime | None:
    return datetime.fromtimestamp(value, UTC).replace(tzinfo=None) if value else None


class WebhookService:
    """Verifies Stripe webhooks, dedups them via the webhook_events store, and
    projects the ones we care about onto the user's subscription."""

    def __init__(self, session: AsyncSession) -> None:
        self.subscriptions = SubscriptionRepository(session)
        self.payments = PaymentRepository(session)
        self.events = WebhookEventRepository(session)

    async def handle_stripe(self, payload: bytes, signature: str) -> None:
        cfg = settings.payments
        provider = StripeProvider(cfg.STRIPE_API_KEY, cfg.STRIPE_WEBHOOK_SECRET)
        envelope = provider.verify_webhook(payload, signature)  # raises on bad signature

        # Idempotency: Stripe retries deliver the same event id.
        seen = await self.events.get_by_event(PaymentProvider.STRIPE.value, envelope.event_id)
        if seen and seen.status == "PROCESSED":
            return
        if not seen:
            seen = await self.events.create_one(
                {
                    "provider": PaymentProvider.STRIPE.value,
                    "event_id": envelope.event_id,
                    "event_type": envelope.event_type,
                    "payload": envelope.data,
                }
            )

        try:
            await self._dispatch(envelope.event_type, envelope.data)
        except Exception as e:  # keep the store consistent; let the caller 500 so Stripe retries
            await self.events.update_one(seen, {"status": "FAILED", "error": str(e)})
            raise
        await self.events.update_one(
            seen, {"status": "PROCESSED", "processed_at": datetime.now(UTC).replace(tzinfo=None)}
        )

    async def _dispatch(self, event_type: str, obj: dict) -> None:
        if event_type == "checkout.session.completed":
            await self._on_checkout_completed(obj)
        elif event_type in (
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ):
            await self._on_subscription_changed(obj)
        elif event_type == "invoice.paid":
            await self._on_invoice_paid(obj)
        else:
            logger.info("Ignoring unhandled Stripe event %s", event_type)

    async def _on_checkout_completed(self, obj: dict) -> None:
        meta = obj.get("metadata") or {}
        user_id = obj.get("client_reference_id") or meta.get("user_id")
        plan_uuid = meta.get("plan_uuid")
        if not user_id or not plan_uuid:
            logger.warning("checkout.session.completed missing user/plan metadata")
            return
        await self._upsert_subscription(
            user_id=int(user_id),
            plan_uuid=UUID(plan_uuid),
            provider_subscription_id=obj.get("subscription"),
            status=SubscriptionStatus.ACTIVE,
        )

    async def _on_subscription_changed(self, obj: dict) -> None:
        sub = await self.subscriptions.get_by_provider_id(obj.get("id"))
        if not sub:
            # No local row yet (checkout webhook not seen); metadata still lets us create it.
            meta = obj.get("metadata") or {}
            if meta.get("user_id") and meta.get("plan_uuid"):
                await self._upsert_subscription(
                    user_id=int(meta["user_id"]),
                    plan_uuid=UUID(meta["plan_uuid"]),
                    provider_subscription_id=obj.get("id"),
                    status=_STRIPE_STATUS.get(obj.get("status"), SubscriptionStatus.ACTIVE),
                )
            return
        # A portal "cancel at end of period" sets `cancel_at` (a date), not
        # `cancel_at_period_end`, so treat either as "will not renew". Show the
        # end date from `cancel_at` when present, else the current period end.
        cancel_at = obj.get("cancel_at")
        will_cancel = bool(obj.get("cancel_at_period_end")) or cancel_at is not None
        end = _ts(cancel_at) if cancel_at else _ts(obj.get("current_period_end"))
        await self.subscriptions.update_one(
            sub,
            {
                "status": _STRIPE_STATUS.get(obj.get("status"), sub.status).value,
                "current_period_end": end,
                "cancel_at_period_end": will_cancel,
                "canceled_at": _ts(obj.get("canceled_at")),
            },
        )

    async def _on_invoice_paid(self, obj: dict) -> None:
        invoice_id = obj.get("id")
        if invoice_id and await self.payments.get_by_provider_id(invoice_id):
            return
        sub = None
        if obj.get("subscription"):
            sub = await self.subscriptions.get_by_provider_id(obj["subscription"])
        await self.payments.create_one(
            {
                "user_id": sub.user_id if sub else None,
                "subscription_uuid": sub.uuid if sub else None,
                "provider": PaymentProvider.STRIPE.value,
                "provider_payment_id": invoice_id,
                "amount_cents": obj.get("amount_paid", 0),
                "currency": (obj.get("currency") or settings.payments.CURRENCY).upper(),
                "status": PaymentStatus.SUCCEEDED.value,
            }
        )

    async def _upsert_subscription(
        self, *, user_id: int, plan_uuid: UUID, provider_subscription_id, status: SubscriptionStatus
    ) -> None:
        existing = await self.subscriptions.get_for_user(user_id)
        data = {
            "plan_uuid": plan_uuid,
            "provider": PaymentProvider.STRIPE.value,
            "provider_subscription_id": provider_subscription_id,
            "status": status.value,
        }
        if existing:
            await self.subscriptions.update_one(existing, data)
        else:
            await self.subscriptions.create_one({"user_id": user_id, **data})


async def get_webhook_service(session: AsyncSession = Depends(get_session)) -> WebhookService:
    return WebhookService(session)
