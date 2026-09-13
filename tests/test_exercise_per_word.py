"""A newly saved word gets its OWN full set of exercises.

The pool tops up to a global target, which suits someone adding words one at a
time and fails anyone adding many: forty imported words shared five exercises
between them, so practice stopped to wait for the model at almost every card.
Capture now builds the whole set for the word just saved.
"""

from sqlalchemy import select

from app.core.exc import AIProviderError
from app.enums.learning import ExerciseStatus, ExerciseType
from app.models import Exercise, UserWord
from app.schemas.exercise import ExercisePreferences
from app.services.learning.exercise_service import ExercisePoolService
from tests.test_exercises import StubGenerator, _seed_vocab

# Every supported type except MATCH_PAIRS, which is a session over many words.
PER_WORD_TYPES = [ExerciseType.FILL_IN_BLANKS, ExerciseType.MULTIPLE_CHOICE, ExerciseType.FLASHCARD]


async def _one_word(session, email: str, lemma: str = "resilient") -> tuple[int, UserWord]:
    """One user with one word. The lemma varies because `words` is keyed by
    (lemma, language) and shared across accounts."""
    user_id = await _seed_vocab(session, email, [lemma], with_context=True)
    user_word = (await session.execute(select(UserWord).where(UserWord.user_id == user_id))).scalar_one()
    return user_id, user_word


async def _only(service, user_id: int, types: list[ExerciseType]) -> None:
    """Narrow the enabled types so a test asserts on a known set."""
    await service.set_preferences(user_id, ExercisePreferences(exercise_types=types))


# --- the set ---------------------------------------------------------------


async def test_every_enabled_type_is_built_for_the_new_word(sessionmaker):
    async with sessionmaker() as session:
        service = ExercisePoolService(session, StubGenerator())
        user_id, user_word = await _one_word(session, "perword@x.io")
        await _only(service, user_id, PER_WORD_TYPES)

        created = await service.generate_for_word(user_id, user_word.uuid)

        rows = (await session.execute(select(Exercise).where(Exercise.user_id == user_id))).scalars().all()
        assert created == len(PER_WORD_TYPES)
        assert {ExerciseType(r.exercise_type) for r in rows} == set(PER_WORD_TYPES)
        # All about the word just saved, not whatever the pool felt like.
        assert {r.word_uuid for r in rows} == {user_word.word_uuid}


async def test_match_pairs_is_not_part_of_a_single_word_set(sessionmaker):
    """A round spans many words, so it belongs to the pool refill, not here."""
    async with sessionmaker() as session:
        service = ExercisePoolService(session, StubGenerator())
        user_id, user_word = await _one_word(session, "nopairs@x.io")
        await _only(service, user_id, [*PER_WORD_TYPES, ExerciseType.MATCH_PAIRS])

        await service.generate_for_word(user_id, user_word.uuid)

        rows = (await session.execute(select(Exercise).where(Exercise.user_id == user_id))).scalars().all()
        assert ExerciseType.MATCH_PAIRS.value not in {r.exercise_type for r in rows}


async def test_a_full_pool_no_longer_starves_the_new_word(sessionmaker):
    """The whole point: the old refill stopped at a global target, so a word
    added to an already-full pool got nothing of its own."""
    from app.core import settings

    async with sessionmaker() as session:
        service = ExercisePoolService(session, StubGenerator())
        user_id, user_word = await _one_word(session, "starved@x.io")
        await _only(service, user_id, PER_WORD_TYPES)

        # Fill the pool well past its target using other means.
        for _ in range(settings.exercises.EXERCISE_POOL_TARGET + 2):
            session.add(
                Exercise(
                    user_id=user_id,
                    exercise_type=ExerciseType.FLASHCARD.value,
                    prompt="x",
                    answer="x",
                    payload={},
                    language="en",
                )
            )
        await session.flush()

        created = await service.generate_for_word(user_id, user_word.uuid)
        assert created == len(PER_WORD_TYPES)


# --- limits and failures ---------------------------------------------------


async def test_an_unknown_word_is_a_no_op(sessionmaker):
    from uuid import uuid4

    async with sessionmaker() as session:
        service = ExercisePoolService(session, StubGenerator())
        user_id, _ = await _one_word(session, "ghost@x.io")

        assert await service.generate_for_word(user_id, uuid4()) == 0


async def test_a_word_from_another_account_is_a_no_op(sessionmaker):
    """generate_for_word is reached from a task, so it re-checks ownership."""
    async with sessionmaker() as session:
        service = ExercisePoolService(session, StubGenerator())
        mine, _ = await _one_word(session, "mine@x.io", lemma="mineword")
        _, their_word = await _one_word(session, "theirs@x.io", lemma="theirword")

        assert await service.generate_for_word(mine, their_word.uuid) == 0


async def test_a_daily_budget_caps_one_word(sessionmaker, monkeypatch):
    """A free account must not spend its whole allowance on a single word."""
    async with sessionmaker() as session:
        service = ExercisePoolService(session, StubGenerator())
        user_id, user_word = await _one_word(session, "budget@x.io")
        await _only(service, user_id, PER_WORD_TYPES)

        async def budget(_user_id):
            return 2

        monkeypatch.setattr(service.usage, "generation_budget", budget)
        monkeypatch.setattr(service.usage, "consume_generations", lambda *a, **k: _noop())

        assert await service.generate_for_word(user_id, user_word.uuid) == 2


async def test_a_spent_budget_builds_nothing(sessionmaker, monkeypatch):
    async with sessionmaker() as session:
        service = ExercisePoolService(session, StubGenerator())
        user_id, user_word = await _one_word(session, "spent@x.io")

        async def budget(_user_id):
            return 0

        monkeypatch.setattr(service.usage, "generation_budget", budget)
        assert await service.generate_for_word(user_id, user_word.uuid) == 0


async def test_one_failing_type_does_not_lose_the_others(sessionmaker):
    """A gateway that refuses a flashcard must still leave the other cards."""

    class _OneBadType(StubGenerator):
        # Not the flashcard: with a cached translation that one is built
        # without ever reaching the gateway.
        async def generate_fill_in_blank(self, params):
            raise AIProviderError("gateway down")

    async with sessionmaker() as session:
        service = ExercisePoolService(session, _OneBadType())
        user_id, user_word = await _one_word(session, "partial@x.io")
        await _only(service, user_id, PER_WORD_TYPES)

        created = await service.generate_for_word(user_id, user_word.uuid)
        assert 0 < created < len(PER_WORD_TYPES)


async def _noop() -> None:
    return None


async def test_capture_builds_the_new_words_exercises(app, client, monkeypatch):
    """Wiring: the capture route hands over the id of the word just saved."""
    from app.core import settings
    from tests.test_capture import _login

    monkeypatch.setattr(settings.exercises, "EXERCISE_POOL_AUTOFILL", True)
    headers = await _login(app, client)

    calls = []
    monkeypatch.setattr(
        "app.routers.capture.schedule_word_exercises",
        lambda bg, user_id, user_word_uuid: calls.append(user_word_uuid),
    )
    resp = await client.post(
        "/api/vocabulary",
        json={"word": "resilient", "language": "en", "sentence": "She stayed resilient."},
        headers=headers,
    )

    assert resp.status_code == 201
    assert len(calls) == 1
    assert str(calls[0]) == resp.json()["uuid"]  # this word, not a pool top-up


# --- catching up what was never built --------------------------------------


async def test_backfill_finds_a_word_with_no_exercises(sessionmaker, monkeypatch):
    """Generation happens once, at capture. A word saved while the daily
    allowance was spent is never revisited — this is what goes back for it."""
    monkeypatch.setattr("app.services.learning.model_busy.model_is_busy", _never_busy)

    async with sessionmaker() as session:
        service = ExercisePoolService(session, StubGenerator())
        user_id, user_word = await _one_word(session, "backfill@x.io")
        await _only(service, user_id, PER_WORD_TYPES)

        created = await service.backfill_missing(user_id)

        rows = (await session.execute(select(Exercise).where(Exercise.user_id == user_id))).scalars().all()
        assert created == len(PER_WORD_TYPES)
        assert {r.word_uuid for r in rows} == {user_word.word_uuid}


async def test_backfill_leaves_a_complete_word_alone(sessionmaker, monkeypatch):
    monkeypatch.setattr("app.services.learning.model_busy.model_is_busy", _never_busy)

    async with sessionmaker() as session:
        service = ExercisePoolService(session, StubGenerator())
        user_id, user_word = await _one_word(session, "already@x.io")
        await _only(service, user_id, PER_WORD_TYPES)
        await service.generate_for_word(user_id, user_word.uuid)

        assert await service.backfill_missing(user_id) == 0  # nothing left to do


async def test_backfill_completes_a_partial_set(sessionmaker, monkeypatch):
    """The realistic case: a budget that ran out mid-word."""
    monkeypatch.setattr("app.services.learning.model_busy.model_is_busy", _never_busy)

    async with sessionmaker() as session:
        service = ExercisePoolService(session, StubGenerator())
        user_id, user_word = await _one_word(session, "partialset@x.io")

        # Build one type only — the shape a spent budget leaves behind — then
        # widen the preferences and let the backfill notice the gap.
        await _only(service, user_id, [PER_WORD_TYPES[0]])
        await service.generate_for_word(user_id, user_word.uuid)
        await _only(service, user_id, PER_WORD_TYPES)

        created = await service.backfill_missing(user_id)

        rows = (await session.execute(select(Exercise).where(Exercise.user_id == user_id))).scalars().all()
        assert created == len(PER_WORD_TYPES) - 1  # only what was missing
        assert {ExerciseType(r.exercise_type) for r in rows} == set(PER_WORD_TYPES)


async def test_a_completed_exercise_still_counts_as_built(sessionmaker, monkeypatch):
    """Otherwise practising a word would make the backfill rebuild it forever."""
    monkeypatch.setattr("app.services.learning.model_busy.model_is_busy", _never_busy)

    async with sessionmaker() as session:
        service = ExercisePoolService(session, StubGenerator())
        user_id, user_word = await _one_word(session, "answered@x.io")
        await _only(service, user_id, PER_WORD_TYPES)
        await service.generate_for_word(user_id, user_word.uuid)

        for row in (await session.execute(select(Exercise).where(Exercise.user_id == user_id))).scalars():
            row.status = ExerciseStatus.COMPLETED.value
        await session.flush()

        assert await service.backfill_missing(user_id) == 0


async def test_backfill_stands_aside_for_a_learner(sessionmaker, monkeypatch):
    """Catch-up on the same single model somebody may be waiting on."""

    async def busy():
        return True

    monkeypatch.setattr("app.services.learning.model_busy.model_is_busy", busy)

    async with sessionmaker() as session:
        service = ExercisePoolService(session, StubGenerator())
        user_id, _ = await _one_word(session, "yield@x.io")
        await _only(service, user_id, PER_WORD_TYPES)

        assert await service.backfill_missing(user_id) == 0


async def test_backfill_is_capped_per_run(sessionmaker, monkeypatch):
    monkeypatch.setattr("app.services.learning.model_busy.model_is_busy", _never_busy)

    async with sessionmaker() as session:
        service = ExercisePoolService(session, StubGenerator())
        user_id = await _seed_vocab(session, "many@x.io", ["alpha", "beta", "gamma"], with_context=True)
        await _only(service, user_id, PER_WORD_TYPES)

        created = await service.backfill_missing(user_id, limit=1)
        assert created == len(PER_WORD_TYPES)  # exactly one word's worth


def test_backfill_runs_on_the_warm_queue_and_a_schedule():
    """It must never sit in front of a refill a learner is waiting on."""
    from app.celery.config import celery_app

    assert celery_app.conf.task_routes["ai.backfill_exercises"] == {"queue": "warm"}
    entry = celery_app.conf.beat_schedule["backfill-missing-exercises"]
    assert entry["task"] == "ai.backfill_exercises"
    assert entry["options"]["expires"] > 0


async def _never_busy() -> bool:
    return False


async def test_generating_twice_for_one_word_is_free(sessionmaker):
    """Idempotent, so a re-run of an import — or a backfill over a half-built
    set — never pays the model for what is already there."""
    async with sessionmaker() as session:
        service = ExercisePoolService(session, StubGenerator())
        user_id, user_word = await _one_word(session, "twice@x.io")
        await _only(service, user_id, PER_WORD_TYPES)

        first = await service.generate_for_word(user_id, user_word.uuid)
        second = await service.generate_for_word(user_id, user_word.uuid)

        assert first == len(PER_WORD_TYPES)
        assert second == 0
