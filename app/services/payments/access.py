"""Whether a subscription currently grants paid access.

Shared by the subscription readout and the usage-limit checks so 'is premium'
is decided in exactly one place — including expiring a trial whose end has
passed even if its status row still says TRIALING (no cron needed)."""

from datetime import UTC, datetime

from app.enums.payments import ACTIVE_SUBSCRIPTION_STATUSES, SubscriptionStatus


def is_active_subscription(sub) -> bool:
    if not sub:
        return False
    status = SubscriptionStatus(sub.status)
    if status not in ACTIVE_SUBSCRIPTION_STATUSES:
        return False
    # A trial only counts while it hasn't ended yet.
    if status == SubscriptionStatus.TRIALING and sub.trial_end_at is not None:
        now = datetime.now(UTC).replace(tzinfo=None)
        if sub.trial_end_at < now:
            return False
    return True
