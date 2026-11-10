"""An instance with no plan can still sell a subscription.

Plans are configuration rather than user data, so emptying the database takes
them with it and checkout fails with nothing in the interface to explain why.
This runs on every container start and fills the gap exactly once.
"""

import pytest

from app.core import settings
from app.enums.payments import PaymentProvider
from app.repositories.plan import PlanRepository
from scripts.bootstrap_plan import ensure_plan

PRICE_ID = "price_test_123"


@pytest.fixture
def configured(monkeypatch, sessionmaker):
    monkeypatch.setattr(settings.payments, "PLAN_BOOTSTRAP_STRIPE_PRICE_ID", PRICE_ID)
    monkeypatch.setattr("app.database.postgres.async_session", sessionmaker)


async def test_no_price_id_means_no_plan(monkeypatch, sessionmaker):
    """A plan row without a price id looks configured and fails at checkout —
    a worse failure than having no plan at all."""
    monkeypatch.setattr(settings.payments, "PLAN_BOOTSTRAP_STRIPE_PRICE_ID", "")
    monkeypatch.setattr("app.database.postgres.async_session", sessionmaker)

    assert await ensure_plan() == "not configured"
    async with sessionmaker() as session:
        _, total = await PlanRepository(session).get_many(limit=1)
        assert total == 0


async def test_an_empty_instance_gets_a_plan(configured, sessionmaker):
    result = await ensure_plan()

    assert "created" in result
    async with sessionmaker() as session:
        plan = await PlanRepository(session).get_by_code(settings.payments.PLAN_BOOTSTRAP_CODE)
        assert plan is not None
        assert plan.is_active is True
        # The price id is what makes it usable; without it checkout cannot run.
        assert plan.provider_price_ids == {PaymentProvider.STRIPE.value: PRICE_ID}


async def test_running_again_changes_nothing(configured, sessionmaker):
    """It runs on every container start, so this is the normal case."""
    await ensure_plan()
    assert "already exist" in await ensure_plan()

    async with sessionmaker() as session:
        _, total = await PlanRepository(session).get_many(limit=10)
        assert total == 1


async def test_an_existing_plan_is_left_alone(configured, sessionmaker):
    """Somebody edited the price in the admin panel; the seed must not undo it."""
    from app.models import Plan

    async with sessionmaker() as session:
        session.add(Plan(code="hand_made", tier="PREMIUM", interval="MONTHLY", price_cents=1, currency="EUR"))
        await session.commit()

    assert "already exist" in await ensure_plan()
    async with sessionmaker() as session:
        assert await PlanRepository(session).get_by_code("hand_made") is not None
        assert await PlanRepository(session).get_by_code(settings.payments.PLAN_BOOTSTRAP_CODE) is None


async def test_the_seeded_plan_is_offered_by_the_api(configured, client):
    """End to end: the point is a plan the client can actually buy."""
    await ensure_plan()

    resp = await client.get("/api/payments/plans")
    assert resp.status_code == 200
    assert [p["code"] for p in resp.json()] == [settings.payments.PLAN_BOOTSTRAP_CODE]
