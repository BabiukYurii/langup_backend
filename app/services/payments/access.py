"""Whether a subscription currently grants paid access.

Shared by the subscription readout and the usage-limit checks so 'is premium'
is decided in exactly one place — including expiring a period that has run out
even if the status row still says ACTIVE or TRIALING (no cron needed)."""

from datetime import UTC, datetime, timedelta

from app.core import settings
from app.enums.payments import ACTIVE_SUBSCRIPTION_STATUSES, SubscriptionStatus


def is_active_subscription(sub) -> bool:
    if not sub:
        return False
    status = SubscriptionStatus(sub.status)
    if status not in ACTIVE_SUBSCRIPTION_STATUSES:
        return False

    now = datetime.now(UTC).replace(tzinfo=None)

    # A trial only counts while it hasn't ended yet.
    if status == SubscriptionStatus.TRIALING and sub.trial_end_at is not None and sub.trial_end_at < now:
        return False

    # Neither does a paid period that has run out. The row stays ACTIVE until a
    # renewal webhook moves the period forward, so without this a webhook that
    # never arrived would hand out premium forever — an account was doing
    # exactly that, ACTIVE with a period that had ended two weeks earlier.
    #
    # The grace covers the ordinary case of a renewal landing late: Stripe
    # retries, and cutting off a paying customer over a few minutes of webhook
    # lag is the worse mistake. A row with no period end is left alone — some
    # are created before the first invoice sets one.
    if sub.current_period_end is not None:
        if sub.current_period_end + timedelta(days=settings.payments.GRACE_DAYS) < now:
            return False

    return True
