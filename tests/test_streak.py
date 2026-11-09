"""Days in a row, under "skip a day, but not two".

The rule is the feature. A streak that dies on one missed evening is a
retention risk for an adult studying alone — losing a forty-day run is the
moment people stop opening the app — so one day of slack is deliberate.
"""

from datetime import UTC, date, datetime, timedelta

from app.services.learning.streak import (
    current_streak,
    days_left,
    local_days,
    longest_streak,
)

TODAY = date(2026, 11, 9)


def days(*offsets: int) -> set[date]:
    """Active days, given as how many days BEFORE today each one is."""
    return {TODAY - timedelta(days=n) for n in offsets}


# --- the current run -------------------------------------------------------


def test_nothing_practised_is_no_streak():
    assert current_streak(set(), TODAY) == 0


def test_today_alone_is_a_streak_of_one():
    assert current_streak(days(0), TODAY) == 1


def test_consecutive_days_count_up():
    assert current_streak(days(0, 1, 2, 3), TODAY) == 4


def test_not_having_practised_yet_today_does_not_end_it():
    """Today is still in progress; a counter that zeroed at midnight would be
    telling the learner they had already failed."""
    assert current_streak(days(1, 2, 3), TODAY) == 3


def test_one_skipped_day_is_forgiven():
    """Every other day keeps it: practised today and two days ago."""
    assert current_streak(days(0, 2, 4, 6), TODAY) == 4


def test_two_skipped_days_end_it():
    assert current_streak(days(3, 4, 5), TODAY) == 0


def test_the_run_stops_at_the_first_gap_of_three():
    """Everything before the break is history, not part of this run."""
    assert current_streak(days(0, 1, 5, 6, 7), TODAY) == 2


def test_a_day_in_the_future_is_ignored():
    """A device with a wrong clock must not inflate the count."""
    assert current_streak(days(0, 1) | {TODAY + timedelta(days=5)}, TODAY) == 2


# --- the best ever ---------------------------------------------------------


def test_the_longest_run_survives_a_lapse():
    """What was earned stays earned — that is the point of showing it."""
    active = days(0, 1) | days(20, 21, 22, 23, 24)
    assert current_streak(active, TODAY) == 2
    assert longest_streak(active) == 5


def test_the_longest_run_uses_the_same_forgiveness():
    assert longest_streak(days(10, 12, 14, 16)) == 4


def test_no_history_is_zero_not_one():
    assert longest_streak(set()) == 0


# --- how long is left ------------------------------------------------------


def test_practised_today_leaves_the_full_allowance():
    """Counts the days, today included, on which practising still saves the run."""
    assert days_left(days(0), TODAY) == 3


def test_missing_today_leaves_today_and_tomorrow():
    assert days_left(days(1), TODAY) == 2


def test_today_is_the_last_chance_after_a_skipped_day():
    """1 is what a reminder needs in order to say something true and urgent."""
    assert days_left(days(2), TODAY) == 1


def test_a_lapsed_run_has_nothing_left():
    assert days_left(days(9), TODAY) == 0


# --- whose midnight --------------------------------------------------------


def test_the_learners_timezone_decides_the_day():
    """Half past midnight in Kyiv is the previous day in UTC. Counting in UTC
    would break a streak the learner had in fact kept."""
    just_after_midnight_kyiv = datetime(2026, 11, 9, 22, 30, tzinfo=UTC).replace(tzinfo=None)

    in_utc = local_days([just_after_midnight_kyiv], 0)
    in_kyiv = local_days([just_after_midnight_kyiv], 120)

    assert in_utc == {date(2026, 11, 9)}
    assert in_kyiv == {date(2026, 11, 10)}


def test_several_attempts_on_one_day_count_once():
    morning = datetime(2026, 11, 9, 8, 0)
    evening = datetime(2026, 11, 9, 21, 0)
    assert local_days([morning, evening]) == {date(2026, 11, 9)}


# --- through the endpoint --------------------------------------------------


async def test_the_endpoint_needs_a_login(client):
    assert (await client.get("/api/review/streak")).status_code == 401


async def test_the_endpoint_reports_the_run(client, session):
    from app.models import Exercise, ExerciseAttempt
    from app.repositories.user import UserRepository

    await client.post("/api/users", json={"email": "streak@x.io", "password": "supersecret123"})
    login = await client.post("/api/auth/login", json={"email": "streak@x.io", "password": "supersecret123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    user = await UserRepository(session).get_by_email("streak@x.io")

    exercise = Exercise(user_id=user.id, exercise_type="FLASHCARD", prompt="p", answer="a", payload={}, language="en")
    session.add(exercise)
    await session.flush()
    now = datetime.now(UTC).replace(tzinfo=None)
    for offset in (0, 1, 3):  # today, yesterday, and one across a skipped day
        session.add(
            ExerciseAttempt(
                user_id=user.id,
                exercise_uuid=exercise.uuid,
                result="CORRECT",
                created_at=now - timedelta(days=offset),
            )
        )
    await session.commit()

    resp = await client.get("/api/review/streak", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["current"] == 3  # the skipped day is forgiven
    assert body["practised_today"] is True
    assert body["longest"] >= 3
    assert body["days_left"] == 3
