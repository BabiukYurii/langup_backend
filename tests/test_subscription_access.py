"""Who counts as premium, and for how long.

`is_active_subscription` is the single place that decides it, so every way a
subscription can lapse has to be handled here — there is no cron sweeping stale
rows, and the row itself keeps saying ACTIVE until a renewal webhook moves the
period forward.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.core import settings
from app.enums.payments import SubscriptionStatus
from app.services.payments.access import is_active_subscription


class _Sub:
    """Only the fields the check reads."""

    def __init__(self, status, trial_end_at=None, current_period_end=None):
        self.status = status.value if hasattr(status, "value") else status
        self.trial_end_at = trial_end_at
        self.current_period_end = current_period_end


def _days(n: int) -> datetime:
    """n days from now, naive UTC like the DB columns."""
    return datetime.now(UTC).replace(tzinfo=None) + timedelta(days=n)


# --- the ordinary cases ----------------------------------------------------


def test_no_subscription_is_not_premium():
    assert is_active_subscription(None) is False


def test_an_active_period_still_running_is_premium():
    assert is_active_subscription(_Sub(SubscriptionStatus.ACTIVE, current_period_end=_days(20))) is True


def test_a_running_trial_is_premium():
    assert is_active_subscription(_Sub(SubscriptionStatus.TRIALING, trial_end_at=_days(3))) is True


def test_an_ended_trial_is_not():
    assert is_active_subscription(_Sub(SubscriptionStatus.TRIALING, trial_end_at=_days(-1))) is False


@pytest.mark.parametrize(
    "status",
    [s for s in SubscriptionStatus if s not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING)],
)
def test_no_other_status_grants_access(status):
    assert is_active_subscription(_Sub(status, current_period_end=_days(20))) is False


# --- the hole this closed --------------------------------------------------


def test_an_active_row_whose_period_ran_out_is_not_premium():
    """The bug, pinned. A renewal webhook that never arrives leaves the row
    ACTIVE forever; one live account had been premium for two weeks on a period
    that ended in August."""
    long_gone = _days(-(settings.payments.GRACE_DAYS + 14))
    assert is_active_subscription(_Sub(SubscriptionStatus.ACTIVE, current_period_end=long_gone)) is False


def test_a_renewal_landing_late_does_not_cut_anyone_off():
    """Stripe retries. Losing a paying customer over minutes of webhook lag is
    the worse mistake, so the period keeps working through the grace window."""
    just_lapsed = _days(-1)
    assert settings.payments.GRACE_DAYS >= 1, "the grace only means something above zero"
    assert is_active_subscription(_Sub(SubscriptionStatus.ACTIVE, current_period_end=just_lapsed)) is True


def test_the_grace_window_does_eventually_close(monkeypatch):
    monkeypatch.setattr(settings.payments, "GRACE_DAYS", 3)
    assert is_active_subscription(_Sub(SubscriptionStatus.ACTIVE, current_period_end=_days(-2))) is True
    assert is_active_subscription(_Sub(SubscriptionStatus.ACTIVE, current_period_end=_days(-4))) is False


def test_a_zero_grace_expires_the_moment_the_period_ends(monkeypatch):
    monkeypatch.setattr(settings.payments, "GRACE_DAYS", 0)
    assert is_active_subscription(_Sub(SubscriptionStatus.ACTIVE, current_period_end=_days(-1))) is False


def test_a_subscription_without_a_period_end_is_left_alone():
    """Some rows exist before the first invoice sets a period; those must not
    be locked out by a check meant for lapsed ones."""
    assert is_active_subscription(_Sub(SubscriptionStatus.ACTIVE, current_period_end=None)) is True


def test_a_lapsed_period_beats_a_trial_that_is_still_running():
    """Both clocks are checked, not whichever matches the status."""
    sub = _Sub(
        SubscriptionStatus.TRIALING,
        trial_end_at=_days(5),
        current_period_end=_days(-(settings.payments.GRACE_DAYS + 5)),
    )
    assert is_active_subscription(sub) is False
