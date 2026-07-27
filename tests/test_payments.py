import json

import pytest

from app.models import Plan
from app.services.payments.providers.base import WebhookEnvelope

pytestmark = pytest.mark.asyncio


# A stand-in Stripe provider: it trusts the raw JSON body as the event, so tests
# don't need real signatures. Swapped in via monkeypatch.
class FakeStripeProvider:
    def __init__(self, *_a, **_k) -> None:
        pass

    def verify_webhook(self, payload: bytes, signature: str) -> WebhookEnvelope:
        e = json.loads(payload)
        return WebhookEnvelope(event_id=e["id"], event_type=e["type"], data=e["data"]["object"])


async def _login(client, email="buyer@x.com"):
    await client.post("/api/users", json={"email": email, "password": "supersecret123"})
    login = await client.post("/api/auth/login", json={"email": email, "password": "supersecret123"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _seed_plan(session, code="premium_monthly", price_id="price_123"):
    plan = Plan(
        code=code,
        tier="PREMIUM",
        interval="MONTHLY",
        price_cents=1999,
        currency="PLN",
        provider_price_ids={"STRIPE": price_id},
        is_active=True,
    )
    session.add(plan)
    await session.flush()
    return plan


def _checkout_event(user_id, plan_uuid, sub_id="sub_1"):
    return {
        "id": "evt_checkout_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": str(user_id),
                "subscription": sub_id,
                "metadata": {"user_id": str(user_id), "plan_uuid": str(plan_uuid)},
            }
        },
    }


# --- plans & checkout ------------------------------------------------------


async def test_list_plans(app, client, session):
    await _seed_plan(session)
    resp = await client.get("/api/payments/plans")
    assert resp.status_code == 200
    assert [p["code"] for p in resp.json()] == ["premium_monthly"]


async def test_checkout_requires_auth(client):
    resp = await client.post("/api/payments/checkout", json={"plan_code": "premium_monthly"})
    assert resp.status_code == 401


async def test_checkout_400_when_stripe_not_configured(app, client, session, monkeypatch):
    # Force the "no key" state regardless of the developer's .env.
    from app.core import settings

    monkeypatch.setattr(settings.payments, "STRIPE_API_KEY", "")
    await _seed_plan(session)
    headers = await _login(client)
    resp = await client.post("/api/payments/checkout", json={"plan_code": "premium_monthly"}, headers=headers)
    assert resp.status_code == 400


async def test_checkout_starts_when_configured(app, client, session, monkeypatch):
    from app.core import settings
    from app.services.payments import billing_service

    await _seed_plan(session)
    headers = await _login(client)
    monkeypatch.setattr(settings.payments, "STRIPE_API_KEY", "sk_test_x")

    class FakeProvider:
        def __init__(self, *_a, **_k):
            pass

        async def create_checkout_session(self, **_k):
            from app.services.payments.providers.base import CheckoutSession

            return CheckoutSession(url="https://checkout.stripe.test/s/1", provider_session_id="cs_1")

    monkeypatch.setattr(billing_service, "StripeProvider", FakeProvider)
    resp = await client.post("/api/payments/checkout", json={"plan_code": "premium_monthly"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["checkout_url"].startswith("https://checkout.stripe.test/")


# --- new-user trial --------------------------------------------------------


async def test_new_user_gets_premium_trial(app, client, session):
    await _seed_plan(session)  # the trial plan must exist
    reg = await client.post("/api/auth/register", json={"email": "trial@x.com", "password": "supersecret123"})
    tok = reg.json()["access_token"]
    body = (await client.get("/api/payments/subscription", headers={"Authorization": f"Bearer {tok}"})).json()
    assert body["status"] == "TRIALING"
    assert body["is_active"] is True


async def test_expired_trial_is_not_active(app, client, session):
    from datetime import UTC, datetime, timedelta

    from app.models import Subscription

    plan = await _seed_plan(session)
    headers = await _login(client)  # a plain user (no trial granted via /api/users)
    me = (await client.get("/api/auth/me", headers=headers)).json()
    session.add(
        Subscription(
            user_id=me["id"],
            plan_uuid=plan.uuid,
            status="TRIALING",
            trial_end_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
        )
    )
    await session.flush()
    body = (await client.get("/api/payments/subscription", headers=headers)).json()
    assert body["status"] == "TRIALING"
    assert body["is_active"] is False  # the trial has ended


# --- customer portal -------------------------------------------------------


async def test_portal_requires_auth(client):
    assert (await client.post("/api/payments/portal")).status_code == 401


async def test_portal_400_without_subscription(app, client, session, monkeypatch):
    from app.core import settings

    monkeypatch.setattr(settings.payments, "STRIPE_API_KEY", "sk_test_x")
    headers = await _login(client)
    resp = await client.post("/api/payments/portal", headers=headers)
    assert resp.status_code == 400


async def test_portal_returns_url(app, client, session, monkeypatch):
    from app.core import settings
    from app.models import Subscription
    from app.services.payments import billing_service

    plan = await _seed_plan(session)
    headers = await _login(client)
    me = (await client.get("/api/auth/me", headers=headers)).json()
    session.add(
        Subscription(
            user_id=me["id"], plan_uuid=plan.uuid, provider="STRIPE", provider_subscription_id="sub_1", status="ACTIVE"
        )
    )
    await session.flush()
    monkeypatch.setattr(settings.payments, "STRIPE_API_KEY", "sk_test_x")

    class FakeProvider:
        def __init__(self, *_a, **_k):
            pass

        async def create_billing_portal_session(self, *, subscription_id, return_url):
            assert subscription_id == "sub_1"
            return "https://billing.stripe.test/p/1"

    monkeypatch.setattr(billing_service, "StripeProvider", FakeProvider)
    resp = await client.post("/api/payments/portal", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["portal_url"].startswith("https://billing.stripe.test/")


# --- subscription readout --------------------------------------------------


async def test_subscription_free_by_default(app, client):
    headers = await _login(client)
    resp = await client.get("/api/payments/subscription", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_active"] is False


# --- webhooks --------------------------------------------------------------


async def test_webhook_checkout_activates_subscription(app, client, session, monkeypatch):
    from app.services.payments import webhook_service

    monkeypatch.setattr(webhook_service, "StripeProvider", FakeStripeProvider)
    plan = await _seed_plan(session)
    headers = await _login(client)
    me = (await client.get("/api/auth/me", headers=headers)).json()

    event = _checkout_event(me["id"], plan.uuid)
    resp = await client.post("/api/webhooks/stripe", content=json.dumps(event), headers={"Stripe-Signature": "x"})
    assert resp.status_code == 200

    sub = await client.get("/api/payments/subscription", headers=headers)
    body = sub.json()
    assert body["is_active"] is True
    assert body["status"] == "ACTIVE"
    assert body["plan_code"] == "premium_monthly"


async def test_webhook_is_idempotent(app, client, session, monkeypatch):
    from app.services.payments import webhook_service

    monkeypatch.setattr(webhook_service, "StripeProvider", FakeStripeProvider)
    plan = await _seed_plan(session)
    headers = await _login(client)
    me = (await client.get("/api/auth/me", headers=headers)).json()
    event = _checkout_event(me["id"], plan.uuid)

    for _ in range(2):
        resp = await client.post("/api/webhooks/stripe", content=json.dumps(event), headers={"Stripe-Signature": "x"})
        assert resp.status_code == 200

    # Still exactly one subscription, one webhook_event row.
    from sqlalchemy import func, select

    from app.models import Subscription, WebhookEvent

    subs = (await session.execute(select(func.count()).select_from(Subscription))).scalar()
    events = (await session.execute(select(func.count()).select_from(WebhookEvent))).scalar()
    assert subs == 1
    assert events == 1


async def test_webhook_subscription_updated_changes_status(app, client, session, monkeypatch):
    from app.services.payments import webhook_service

    monkeypatch.setattr(webhook_service, "StripeProvider", FakeStripeProvider)
    plan = await _seed_plan(session)
    headers = await _login(client)
    me = (await client.get("/api/auth/me", headers=headers)).json()

    # First activate via checkout, then a subscription.updated marks it past_due.
    await client.post(
        "/api/webhooks/stripe",
        content=json.dumps(_checkout_event(me["id"], plan.uuid)),
        headers={"Stripe-Signature": "x"},
    )
    updated = {
        "id": "evt_sub_upd_1",
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_1", "status": "past_due", "cancel_at_period_end": True}},
    }
    await client.post("/api/webhooks/stripe", content=json.dumps(updated), headers={"Stripe-Signature": "x"})

    body = (await client.get("/api/payments/subscription", headers=headers)).json()
    assert body["status"] == "PAST_DUE"
    assert body["is_active"] is False
    assert body["cancel_at_period_end"] is True


async def test_webhook_cancel_at_marks_not_renewing(app, client, session, monkeypatch):
    # A portal cancel-at-period-end sets `cancel_at` (a date), not the
    # cancel_at_period_end flag; the subscription stays active until then.
    from app.services.payments import webhook_service

    monkeypatch.setattr(webhook_service, "StripeProvider", FakeStripeProvider)
    plan = await _seed_plan(session)
    headers = await _login(client)
    me = (await client.get("/api/auth/me", headers=headers)).json()
    await client.post(
        "/api/webhooks/stripe",
        content=json.dumps(_checkout_event(me["id"], plan.uuid)),
        headers={"Stripe-Signature": "x"},
    )
    updated = {
        "id": "evt_cancel_at",
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_1", "status": "active", "cancel_at": 1787866092, "cancel_at_period_end": False}},
    }
    await client.post("/api/webhooks/stripe", content=json.dumps(updated), headers={"Stripe-Signature": "x"})

    body = (await client.get("/api/payments/subscription", headers=headers)).json()
    assert body["is_active"] is True  # still active until the cancel date
    assert body["cancel_at_period_end"] is True  # but flagged as not renewing
    assert body["current_period_end"] is not None
