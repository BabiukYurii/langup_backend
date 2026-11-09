"""How many days in a row the learner has practised.

The rule is "skip a day, but not two": practising at least every other day keeps
a streak alive. That is deliberate, and it is the whole reason this is not a
plain consecutive-days counter.

A streak that punishes one missed evening is a retention risk rather than a
feature — for an adult studying on their own, losing a forty-day run is the
moment they stop opening the app at all. One day of slack costs almost nothing
in habit terms and removes that cliff. There is no public comparison with other
learners for the same reason.

Pure functions over a set of dates, so the rule can be tested without a
database, and so the day boundary is decided in one place: the learner's own
local midnight, not the server's.
"""

from datetime import date, datetime, timedelta

# The most recent practice day may be this many days back and still count. 2
# means "today, yesterday, or the day before" — one skipped day, not two.
_MAX_GAP_DAYS = 2

# How far back the streak is measured. A year of history is more than anyone
# needs to see and keeps the query bounded on an account with years of attempts.
HISTORY_DAYS = 400


def local_days(timestamps: list[datetime], tz_offset_minutes: int = 0) -> set[date]:
    """The distinct local dates a list of attempt timestamps falls on.

    The offset matters more than it looks: practising at half past midnight in
    Kyiv is the previous day in UTC, which would silently break a streak the
    learner had in fact kept.
    """
    shift = timedelta(minutes=tz_offset_minutes)
    return {(stamp + shift).date() for stamp in timestamps}


def current_streak(active: set[date], today: date) -> int:
    """Days practised in the run that is still alive, 0 when it has lapsed.

    Counts days actually practised, not the calendar span: a learner who went
    every other day for a fortnight has a streak of seven, which is what they
    did.
    """
    if not active:
        return 0
    recent = [d for d in active if d <= today]
    if not recent:
        return 0
    recent.sort(reverse=True)
    # Today is still in progress, so not having practised yet today cannot end
    # anything; the run only lapses once the allowance itself is used up.
    if (today - recent[0]).days > _MAX_GAP_DAYS:
        return 0

    count = 1
    for previous, following in zip(recent[1:], recent, strict=False):
        if (following - previous).days > _MAX_GAP_DAYS:
            break
        count += 1
    return count


def longest_streak(active: set[date]) -> int:
    """The best run the learner has ever had, under the same rule."""
    if not active:
        return 0
    days = sorted(active)
    best = run = 1
    for previous, following in zip(days, days[1:], strict=False):
        run = run + 1 if (following - previous).days <= _MAX_GAP_DAYS else 1
        best = max(best, run)
    return best


def days_left(active: set[date], today: date) -> int:
    """Days remaining to practise before the current run lapses.

    1 means today is the last chance — which is exactly what a reminder should
    be able to say out loud.
    """
    if not active:
        return 0
    recent = max((d for d in active if d <= today), default=None)
    if recent is None:
        return 0
    spent = (today - recent).days
    return max(0, _MAX_GAP_DAYS - spent + 1) if spent <= _MAX_GAP_DAYS else 0
