"""A paid invoice has to move the subscription's period forward.

It is the only event that reliably says how long the customer has paid for:
`customer.subscription.updated` may not be enabled on the endpoint at all (it
was not on the live one), and `checkout.session.completed` carries no period.
Without this the row keeps whatever period it was created with, and a successful
payment leaves the account reading Free — which is exactly what happened.
"""

import json
from datetime import UTC, datetime, timedelta

from app.services.payments.access import is_active_subscription
from app.services.payments.webhook_service import _invoice_period


def _epoch(days: int) -> int:
    return int((datetime.now(UTC) + timedelta(days=days)).timestamp())


def _invoice(user_id, *, sub_id="sub_new", start_days=0, end_days=30, event_id="evt_inv_1"):
    """An invoice.paid shaped like the real one Stripe sends.

    Note the top-level period: on a first invoice Stripe sets BOTH ends to the
    billing moment, and the span that was paid for is on the line item.
    """
    return {
        "id": event_id,
        "type": "invoice.paid",
        "data": {
            "object": {
                "id": f"in_{event_id}",
                "subscription": sub_id,
                "amount_paid": 999,
                "currency": "usd",
                "period_start": _epoch(start_days),
                "period_end": _epoch(start_days),
                "lines": {"data": [{"period": {"start": _epoch(start_days), "end": _epoch(end_days)}}]},
                "subscription_details": {"metadata": {"user_id": str(user_id)}},
            }
        },
    }


# --- reading the period out of an invoice ----------------------------------


def test_the_period_comes_from_the_line_item():
    """The invoice's own period_end is the billing moment; on a first invoice
    it equals the START, and trusting it would file a fresh payment as expired."""
    invoice = _invoice(1)["data"]["object"]
    start, end = _invoice_period(invoice)

    assert end > start
    assert (end - start).days >= 27  # a month, not zero


def test_an_invoice_without_line_periods_falls_back_to_its_own():
    invoice = {"period_start": _epoch(0), "period_end": _epoch(30), "lines": {"data": []}}
    start, end = _invoice_period(invoice)

    assert start is not None
    assert (end - start).days >= 27


def test_an_invoice_with_no_period_at_all_reports_none():
    assert _invoice_period({}) == (None, None)


# --- end to end through the webhook ----------------------------------------


async def _login(client, email="periodbuyer@x.com"):
    await client.post("/api/users", json={"email": email, "password": "supersecret123"})
    login = await client.post("/api/auth/login", json={"email": email, "password": "supersecret123"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_paying_makes_the_account_premium(app, client, session, monkeypatch):
    """The bug, end to end: Stripe said paid and the account still read Free."""
    from app.services.payments import webhook_service
    from tests.test_payments import FakeStripeProvider, _checkout_event, _seed_plan

    monkeypatch.setattr(webhook_service, "StripeProvider", FakeStripeProvider)
    plan = await _seed_plan(session)
    headers = await _login(client)
    me = (await client.get("/api/auth/me", headers=headers)).json()

    await client.post(
        "/api/webhooks/stripe",
        content=json.dumps(_checkout_event(me["id"], plan.uuid, sub_id="sub_new")),
        headers={"Stripe-Signature": "x"},
    )
    await client.post(
        "/api/webhooks/stripe",
        content=json.dumps(_invoice(me["id"])),
        headers={"Stripe-Signature": "x"},
    )

    body = (await client.get("/api/payments/subscription", headers=headers)).json()
    assert body["is_active"] is True
    assert body["current_period_end"] is not None


async def test_the_period_is_set_even_before_checkout_stores_the_id(app, client, session, monkeypatch):
    """On a first payment `invoice.paid` lands BEFORE checkout has stored the
    new subscription id, so the provider lookup misses; the metadata on the
    invoice is what saves it."""
    from app.services.payments import webhook_service
    from tests.test_payments import FakeStripeProvider, _checkout_event, _seed_plan

    monkeypatch.setattr(webhook_service, "StripeProvider", FakeStripeProvider)
    plan = await _seed_plan(session)
    headers = await _login(client, email="racer@x.com")
    me = (await client.get("/api/auth/me", headers=headers)).json()

    # Establish a row under an OLD provider id, then pay under a new one.
    await client.post(
        "/api/webhooks/stripe",
        content=json.dumps(_checkout_event(me["id"], plan.uuid, sub_id="sub_old")),
        headers={"Stripe-Signature": "x"},
    )
    await client.post(
        "/api/webhooks/stripe",
        content=json.dumps(_invoice(me["id"], sub_id="sub_brand_new", event_id="evt_inv_race")),
        headers={"Stripe-Signature": "x"},
    )

    body = (await client.get("/api/payments/subscription", headers=headers)).json()
    assert body["is_active"] is True


async def test_a_lapsed_row_is_revived_by_a_new_payment(app, client, session, monkeypatch):
    """The live case: an ACTIVE row whose period ended in August, then a fresh
    test-mode payment. The payment has to win."""
    from app.repositories.subscription import SubscriptionRepository
    from app.services.payments import webhook_service
    from tests.test_payments import FakeStripeProvider, _checkout_event, _seed_plan

    monkeypatch.setattr(webhook_service, "StripeProvider", FakeStripeProvider)
    plan = await _seed_plan(session)
    headers = await _login(client, email="lapsed@x.com")
    me = (await client.get("/api/auth/me", headers=headers)).json()

    await client.post(
        "/api/webhooks/stripe",
        content=json.dumps(_checkout_event(me["id"], plan.uuid, sub_id="sub_lapsed")),
        headers={"Stripe-Signature": "x"},
    )
    repo = SubscriptionRepository(session)
    sub = await repo.get_for_user(me["id"])
    await repo.update_one(sub, {"current_period_end": datetime.now(UTC).replace(tzinfo=None) - timedelta(days=60)})
    assert is_active_subscription(await repo.get_for_user(me["id"])) is False

    await client.post(
        "/api/webhooks/stripe",
        content=json.dumps(_invoice(me["id"], sub_id="sub_lapsed", event_id="evt_inv_revive")),
        headers={"Stripe-Signature": "x"},
    )

    body = (await client.get("/api/payments/subscription", headers=headers)).json()
    assert body["is_active"] is True
