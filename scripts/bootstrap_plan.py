#!/usr/bin/env python3
"""Make sure the instance offers a subscription plan.

Plans are configuration rather than user data, so emptying the database takes
them with it — and checkout then fails with nothing in the interface to explain
why. The admin panel can create one, but only after somebody notices.

Run from entrypoint.sh on every container start, behind an "is there already a
plan" check, so every start but the one that needs it is a no-op. Same shape as
bootstrap_admin, and for the same reason: a migration runs once and could not
help the second time a database is emptied.

Does nothing without PLAN_BOOTSTRAP_STRIPE_PRICE_ID. A plan row with no price id
looks configured and then fails at the checkout call, which is a worse failure
than having no plan.

    uv run python -m scripts.bootstrap_plan
"""

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("bootstrap_plan")


async def ensure_plan() -> str:
    """Create the configured plan if the instance has none. Says what happened."""
    from app.core import settings
    from app.database.postgres import async_session
    from app.enums.payments import BillingInterval, PaymentProvider, PlanTier
    from app.repositories.plan import PlanRepository

    cfg = settings.payments
    price_id = (cfg.PLAN_BOOTSTRAP_STRIPE_PRICE_ID or "").strip()
    if not price_id:
        return "not configured"

    async with async_session() as session:
        plans = PlanRepository(session)
        existing, total = await plans.get_many(limit=1)
        if total:
            return f"{total} plan(s) already exist"

        await plans.create_one(
            {
                "code": cfg.PLAN_BOOTSTRAP_CODE,
                "tier": PlanTier.PREMIUM.value,
                "interval": BillingInterval.MONTHLY.value,
                "price_cents": cfg.PLAN_BOOTSTRAP_PRICE_CENTS,
                "currency": cfg.PLAN_BOOTSTRAP_CURRENCY.upper(),
                "trial_days": cfg.PLAN_BOOTSTRAP_TRIAL_DAYS,
                "provider_price_ids": {PaymentProvider.STRIPE.value: price_id},
                "is_active": True,
            }
        )
        return f"created {cfg.PLAN_BOOTSTRAP_CODE} at {cfg.PLAN_BOOTSTRAP_PRICE_CENTS} {cfg.PLAN_BOOTSTRAP_CURRENCY}"


def main() -> int:
    try:
        logger.info("bootstrap_plan: %s", asyncio.run(ensure_plan()))
    except Exception:  # noqa: BLE001 — seeding must never stop the app starting
        logger.exception("bootstrap_plan: failed, carrying on")
    return 0


if __name__ == "__main__":
    sys.exit(main())
