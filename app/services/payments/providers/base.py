from dataclasses import dataclass
from typing import Protocol


@dataclass
class CheckoutSession:
    # Minimal, provider-agnostic result of opening a checkout.
    url: str
    provider_session_id: str


@dataclass
class WebhookEnvelope:
    # A verified inbound webhook, normalized across providers.
    event_id: str
    event_type: str
    data: dict


class PaymentProvider(Protocol):
    """Contract the billing layer depends on, so it stays provider-agnostic."""

    name: str

    async def create_checkout_session(
        self,
        *,
        price_id: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        client_reference_id: str,
        metadata: dict | None = None,
    ) -> CheckoutSession: ...

    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEnvelope: ...
