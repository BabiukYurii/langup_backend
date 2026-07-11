from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core import settings
from app.core.exc import AIProviderError, BadRequestException, ObjectNotFoundException
from app.enums.learning import AttemptResult
from app.models import User, UserWord, Word
from app.schemas.ai import Blank, GeneratedFillInBlank
from app.schemas.exercise import SubmitAttemptRequest
from app.services.auth.oauth_google import get_google_verifier
from app.services.learning.exercise_service import ExercisePoolService

PROFILE = {"sub": "ex-sub-1", "email": "ex@gmail.com", "email_verified": True, "name": "Ex"}


class StubGenerator:
    """Deterministic fill-in-blank for the requested word — no AI, no network."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate_fill_in_blank(self, params):
        self.calls += 1
        word = params.words[0]
        return GeneratedFillInBlank(
            text="Please stay ___1___ today.",
            blanks=[Blank(index=1, answer=word, options=[word, "aaa", "bbb", "ccc"])],
            model="stub",
        )


class FailingGenerator:
    async def generate_fill_in_blank(self, params):
        raise AIProviderError("gateway down")


async def _seed_vocab(session, email: str, words: list[str]) -> int:
    user = User(email=email)
    session.add(user)
    await session.flush()
    for lemma in words:
        word = Word(lemma=lemma, language="en")
        session.add(word)
        await session.flush()
        session.add(UserWord(user_id=user.id, word_uuid=word.uuid))
    await session.commit()
    return user.id


# --- pool refill -----------------------------------------------------------


async def test_replenish_fills_pool_up_to_target(session):
    user_id = await _seed_vocab(session, "a@x.com", ["resilient", "eloquent", "serene", "candid", "prudent", "vivid"])
    service = ExercisePoolService(session, StubGenerator())

    created = await service.replenish(user_id)
    assert created == settings.exercises.EXERCISE_POOL_TARGET
    assert await service.exercises.count_pending(user_id) == settings.exercises.EXERCISE_POOL_TARGET

    # already at target -> nothing added
    assert await service.replenish(user_id) == 0


async def test_served_exercises_still_count_toward_pool_target(session):
    # serving without answering must not trigger extra generation
    user_id = await _seed_vocab(session, "a2@x.com", ["resilient", "eloquent", "serene", "candid", "prudent"])
    service = ExercisePoolService(session, StubGenerator())
    await service.replenish(user_id)

    await service.get_next(user_id)
    assert await service.replenish(user_id) == 0


async def test_replenish_swallows_ai_failure(session):
    user_id = await _seed_vocab(session, "b@x.com", ["resilient"])
    service = ExercisePoolService(session, FailingGenerator())

    assert await service.replenish(user_id) == 0
    assert await service.exercises.count_pending(user_id) == 0


# --- serving from the pool -------------------------------------------------


async def test_get_next_reserves_unanswered_then_moves_on(session):
    user_id = await _seed_vocab(session, "c@x.com", ["resilient", "eloquent"])
    service = ExercisePoolService(session, StubGenerator())
    await service.replenish(user_id)

    first = await service.get_next(user_id)
    assert "___1___" in first.payload["text"]
    # unanswered exercise is re-served (page refresh must not burn the pool)
    again = await service.get_next(user_id)
    assert again.uuid == first.uuid

    # once answered, the next (different) exercise is served
    await service.submit_attempt(user_id, first.uuid, SubmitAttemptRequest(answers={"1": "resilient"}))
    second = await service.get_next(user_id)
    assert second.uuid != first.uuid

    # answering the last one empties the pool
    await service.submit_attempt(user_id, second.uuid, SubmitAttemptRequest(answers={"1": "eloquent"}))
    with pytest.raises(ObjectNotFoundException):
        await service.get_next(user_id)


async def test_get_next_empty_pool_raises(session):
    user_id = await _seed_vocab(session, "d@x.com", [])
    service = ExercisePoolService(session, StubGenerator())
    with pytest.raises(ObjectNotFoundException):
        await service.get_next(user_id)


# --- grading attempts ------------------------------------------------------


async def test_submit_correct_grades_and_updates_mastery(session):
    user_id = await _seed_vocab(session, "e@x.com", ["resilient"])
    service = ExercisePoolService(session, StubGenerator())
    await service.replenish(user_id)
    ex = await service.get_next(user_id)

    result = await service.submit_attempt(user_id, ex.uuid, SubmitAttemptRequest(answers={"1": "resilient"}))
    assert result.is_correct is True
    assert result.result == AttemptResult.CORRECT
    assert result.correct_answers == {"1": "resilient"}
    assert result.mastery_level is not None  # SM-2 was fed for the vocabulary word


async def test_submit_is_case_insensitive(session):
    user_id = await _seed_vocab(session, "e2@x.com", ["resilient"])
    service = ExercisePoolService(session, StubGenerator())
    await service.replenish(user_id)
    ex = await service.get_next(user_id)

    result = await service.submit_attempt(user_id, ex.uuid, SubmitAttemptRequest(answers={"1": "  Resilient "}))
    assert result.is_correct is True


async def test_submit_incorrect(session):
    user_id = await _seed_vocab(session, "f@x.com", ["resilient"])
    service = ExercisePoolService(session, StubGenerator())
    await service.replenish(user_id)
    ex = await service.get_next(user_id)

    result = await service.submit_attempt(user_id, ex.uuid, SubmitAttemptRequest(answers={"1": "wrong"}))
    assert result.is_correct is False
    assert result.result == AttemptResult.INCORRECT
    assert result.correct_answers == {"1": "resilient"}


async def test_submit_twice_is_rejected(session):
    user_id = await _seed_vocab(session, "g@x.com", ["resilient"])
    service = ExercisePoolService(session, StubGenerator())
    await service.replenish(user_id)
    ex = await service.get_next(user_id)
    await service.submit_attempt(user_id, ex.uuid, SubmitAttemptRequest(answers={"1": "resilient"}))

    with pytest.raises(BadRequestException):
        await service.submit_attempt(user_id, ex.uuid, SubmitAttemptRequest(answers={"1": "resilient"}))


async def test_submit_unknown_exercise_raises(session):
    user_id = await _seed_vocab(session, "h@x.com", ["resilient"])
    service = ExercisePoolService(session, StubGenerator())
    with pytest.raises(ObjectNotFoundException):
        await service.submit_attempt(user_id, uuid4(), SubmitAttemptRequest(answers={}))


# --- HTTP wiring -----------------------------------------------------------


async def _login(app, client) -> dict:
    app.dependency_overrides[get_google_verifier] = lambda: lambda _t: PROFILE
    token = (await client.post("/api/auth/google", json={"id_token": "fake"})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_exercises_require_auth(client):
    assert (await client.get("/api/exercises/next")).status_code == 401
    assert (await client.post("/api/exercises/x/attempt", json={"answers": {}})).status_code in (401, 422)


async def test_next_empty_pool_returns_404(app, client):
    headers = await _login(app, client)
    assert (await client.get("/api/exercises/next", headers=headers)).status_code == 404


async def test_http_serve_and_answer_flow(app, client, sessionmaker):
    headers = await _login(app, client)
    await client.post("/api/vocabulary", json={"word": "resilient", "language": "en"}, headers=headers)

    # Seed the pool in a short-lived session, closed before the HTTP calls.
    async with sessionmaker() as s:
        user = (await s.execute(select(User).where(User.email == PROFILE["email"]))).scalar_one()
        await ExercisePoolService(s, StubGenerator()).replenish(user.id)

    nxt = await client.get("/api/exercises/next", headers=headers)
    assert nxt.status_code == 200
    body = nxt.json()
    assert body["exercise_type"] == "FILL_IN_BLANKS"
    assert "answer" not in body  # answer key never leaves the server
    assert "___1___" in body["payload"]["text"]

    answered = await client.post(
        f"/api/exercises/{body['uuid']}/attempt",
        json={"answers": {"1": "resilient"}},
        headers=headers,
    )
    assert answered.status_code == 200
    result = answered.json()
    assert result["is_correct"] is True
    assert result["correct_answers"] == {"1": "resilient"}
