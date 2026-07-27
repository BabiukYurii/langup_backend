import asyncio
import json

import stripe

from app.core.exc import BadRequestException
from app.enums.payments import PaymentProvider as ProviderEnum
from app.services.payments.providers.base import CheckoutSession, WebhookEnvelope


class StripeProvider:
    """Stripe implementation: hosted Checkout + signed webhooks.

    The Stripe SDK is synchronous, so network calls run in a worker thread to
    keep the event loop free.
    """

    name = ProviderEnum.STRIPE.value

    def __init__(self, api_key: str, webhook_secret: str) -> None:
        self._client = stripe.StripeClient(api_key)
        self._webhook_secret = webhook_secret

    async def create_checkout_session(
        self,
        *,
        price_id: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        client_reference_id: str,
        metadata: dict | None = None,
    ) -> CheckoutSession:
        session = await asyncio.to_thread(
            self._client.checkout.sessions.create,
            params={
                "mode": "subscription",
                "line_items": [{"price": price_id, "quantity": 1}],
                "customer_email": customer_email,
                "client_reference_id": client_reference_id,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "subscription_data": {"metadata": metadata or {}},
                "metadata": metadata or {},
            },
        )
        return CheckoutSession(url=session.url, provider_session_id=session.id)

    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEnvelope:
        try:
            # Verifies the signature; raises if it doesn't match.
            stripe.Webhook.construct_event(payload, signature, self._webhook_secret)
        except (ValueError, stripe.SignatureVerificationError) as e:
            # Bad signature or malformed body — never trust it.
            raise BadRequestException("Invalid Stripe webhook signature") from e
        # Parse the raw (already-verified) body ourselves: construct_event returns
        # Stripe objects, which aren't JSON-serializable for the webhook_events store.
        event = json.loads(payload)
        return WebhookEnvelope(event_id=event["id"], event_type=event["type"], data=event["data"]["object"])
