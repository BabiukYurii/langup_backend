from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response

from app.services.payments.webhook_service import WebhookService, get_webhook_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

WebhookServiceDep = Annotated[WebhookService, Depends(get_webhook_service)]


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    service: WebhookServiceDep,
    stripe_signature: str = Header(default="", alias="Stripe-Signature"),
) -> Response:
    """Receive Stripe events. The raw body is needed for signature verification,
    so read it before FastAPI parses anything."""
    payload = await request.body()
    await service.handle_stripe(payload, stripe_signature)
    # 200 tells Stripe we've stored it; a raised error 500s so Stripe retries.
    return Response(status_code=200)
