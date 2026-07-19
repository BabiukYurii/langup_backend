from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core import settings
from app.core.exc import AIProviderError, BadRequestException, ObjectNotFoundException
from app.enums.learning import SUPPORTED_EXERCISE_TYPES, AttemptResult, ExerciseStatus, ExerciseType
from app.models import User, UserWord, Word
from app.schemas.ai import (
    Blank,
    GeneratedFillInBlank,
    GeneratedFlashcard,
    GeneratedMultipleChoice,
    GeneratedTranslation,
)
from app.schemas.exercise import ExercisePreferences, SubmitAttemptRequest
from app.services.auth.oauth_google import get_google_verifier
from app.services.learning.exercise_service import ExercisePoolService, get_exercise_pool_service

PROFILE = {"sub": "ex-sub-1", "email": "ex@gmail.com", "email_verified": True, "name": "Ex"}


class StubGenerator:
    """Deterministic generations for every exercise type — no AI, no network."""

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

    async def generate_multiple_choice(self, params):
        self.calls += 1
        return GeneratedMultipleChoice(
            definition=f"true meaning of {params.word}",
            distractors=["wrong one", "wrong two", "wrong three"],
            model="stub",
        )

    async def generate_flashcard(self, params):
        self.calls += 1
        return GeneratedFlashcard(
            definition=f"true meaning of {params.word}",
            example=f"A sentence with {params.word}.",
            model="stub",
        )

    async def generate_translation(self, params):
        self.calls += 1
        return GeneratedTranslation(translation=f"{params.word}-переклад", model="stub")


class FailingGenerator:
    async def generate_fill_in_blank(self, params):
        raise AIProviderError("gateway down")

    generate_multiple_choice = generate_fill_in_blank
    generate_flashcard = generate_fill_in_blank
    generate_translation = generate_fill_in_blank


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


async def test_replenish_rotates_exercise_types(session):
    user_id = await _seed_vocab(session, "b2@x.com", ["resilient", "eloquent", "serene"])
    service = ExercisePoolService(session, StubGenerator())

    assert await service.replenish(user_id) == 3
    rows, _ = await service.exercises.get_many(user_id=user_id)
    assert {r.exercise_type for r in rows} == {"FILL_IN_BLANKS", "MULTIPLE_CHOICE", "FLASHCARD"}

    # multiple-choice: the correct definition is among the client-facing options
    mc = next(r for r in rows if r.exercise_type == "MULTIPLE_CHOICE")
    assert mc.answer["1"] in mc.payload["options"]
    assert len(mc.payload["options"]) == 4

    # flashcard: card faces in payload, self-grade key as the answer
    fc = next(r for r in rows if r.exercise_type == "FLASHCARD")
    assert fc.payload["front"] in ("resilient", "eloquent", "serene")
    assert fc.payload["back"].startswith("true meaning")
    assert fc.answer == {"1": "know"}


# --- match pairs -----------------------------------------------------------

SIX_WORDS = ["resilient", "eloquent", "serene", "candid", "prudent", "vivid"]


async def _match_pairs_only(session, email: str, words: list[str], generator=None):
    user_id = await _seed_vocab(session, email, words)
    service = ExercisePoolService(session, generator or StubGenerator())
    await service.set_preferences(user_id, ExercisePreferences(exercise_types=[ExerciseType.MATCH_PAIRS]))
    return user_id, service


async def test_match_pairs_round_is_built_from_many_words(session):
    user_id, service = await _match_pairs_only(session, "m1@x.com", SIX_WORDS)

    assert await service.replenish(user_id) > 0
    rows, _ = await service.exercises.get_many(user_id=user_id)
    ex = rows[0]

    assert ex.exercise_type == "MATCH_PAIRS"
    assert ex.word_uuid is None  # a round spans many words
    pairs = ex.payload["pairs"]
    assert len(pairs) == len(SIX_WORDS)
    assert ex.payload["visible"] == settings.exercises.MATCH_PAIRS_VISIBLE
    assert ex.payload["max_mistakes"] == settings.exercises.MATCH_PAIRS_MAX_MISTAKES
    # every pair carries the word it trains, so SM-2 can be fed per pair
    assert all(p["word_uuid"] for p in pairs)
    assert ex.answer == {str(p["id"]): p["translation"] for p in pairs}


async def test_match_pairs_round_is_built_even_when_the_pool_is_full(session):
    # a round must not compete for pool slots: sharing them starved it, because
    # by the time there were enough words the pool was already full
    user_id = await _seed_vocab(session, "m11@x.com", SIX_WORDS)
    service = ExercisePoolService(session, StubGenerator())

    # fill the pool with single-word types only
    await service.set_preferences(user_id, ExercisePreferences(exercise_types=[ExerciseType.FLASHCARD]))
    await service.replenish(user_id)
    assert await service.exercises.count_pending(user_id) >= settings.exercises.EXERCISE_POOL_TARGET

    # enabling match-pairs now still produces a round
    await service.set_preferences(
        user_id, ExercisePreferences(exercise_types=[ExerciseType.FLASHCARD, ExerciseType.MATCH_PAIRS])
    )
    assert await service.replenish(user_id) == 1
    assert await service.exercises.has_pending_of_type(user_id, "MATCH_PAIRS")


async def test_only_one_match_pairs_round_is_queued_at_a_time(session):
    # a round covers many words, so a queue of them would repeat the same ones
    user_id, service = await _match_pairs_only(session, "m10@x.com", SIX_WORDS)

    assert await service.replenish(user_id) == 1
    assert await service.replenish(user_id) == 0

    # answering the pending round frees the slot for a fresh one
    ex = await service.get_next(user_id)
    answers = {str(p["id"]): p["translation"] for p in ex.payload["pairs"]}
    await service.submit_attempt(user_id, ex.uuid, SubmitAttemptRequest(answers=answers))
    assert await service.replenish(user_id) == 1


async def test_match_pairs_uses_scheduled_words_when_few_are_due(session):
    # after practising, SM-2 pushes most words into the future; a round must
    # still be buildable from them instead of starving on the one due word
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.models import UserWord

    user_id, service = await _match_pairs_only(session, "m14@x.com", SIX_WORDS)

    # leave one word due (due_at NULL); schedule every other well ahead
    tomorrow = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=3)
    rows, _ = await service.user_words.list_for_user(user_id, page=1, limit=100)
    for uw in rows[1:]:
        await session.execute(update(UserWord).where(UserWord.uuid == uw.uuid).values(due_at=tomorrow))
    await session.commit()

    assert await service.replenish(user_id, ExerciseType.MATCH_PAIRS) == 1
    stored, _ = await service.exercises.get_many(user_id=user_id)
    ex = next(r for r in stored if r.exercise_type == "MATCH_PAIRS")
    assert len(ex.payload["pairs"]) >= settings.exercises.MATCH_PAIRS_VISIBLE


async def test_match_pairs_skipped_when_vocabulary_is_too_small(session):
    # fewer words than fit on screen -> no round, and it is not an error
    user_id, service = await _match_pairs_only(session, "m2@x.com", ["resilient", "eloquent"])

    assert await service.replenish(user_id) == 0
    assert await service.exercises.count_pending(user_id) == 0


async def test_match_pairs_drops_duplicate_translations(session):
    # two words sharing a translation would make the round ambiguous
    class CollidingGenerator(StubGenerator):
        async def generate_translation(self, params):
            unique = params.word == SIX_WORDS[0]
            return GeneratedTranslation(translation="унікальний" if unique else "той самий", model="stub")

    user_id, service = await _match_pairs_only(session, "m3@x.com", SIX_WORDS, CollidingGenerator())

    # only two distinct translations survive, which is below the visible count
    assert await service.replenish(user_id) == 0


async def test_match_pairs_grading_and_srs(session):
    user_id, service = await _match_pairs_only(session, "m4@x.com", SIX_WORDS)
    await service.replenish(user_id)
    ex = await service.get_next(user_id)

    answers = {str(p["id"]): p["translation"] for p in ex.payload["pairs"]}
    result = await service.submit_attempt(user_id, ex.uuid, SubmitAttemptRequest(answers=answers, mistakes=1))

    assert result.is_correct is True
    assert result.result == AttemptResult.CORRECT
    assert result.mastery_level is None  # many words -> no single mastery to report

    # every matched word was reviewed
    for pair in ex.payload["pairs"]:
        uw = await service.user_words.get_by_user_word(user_id, UUID(pair["word_uuid"]))
        assert uw.last_reviewed_at is not None


async def test_match_pairs_carries_a_time_limit(session):
    user_id, service = await _match_pairs_only(session, "m12@x.com", SIX_WORDS)
    await service.replenish(user_id)
    ex = await service.get_next(user_id)

    assert ex.payload["time_limit"] == settings.exercises.MATCH_PAIRS_TIME_LIMIT_SECONDS


async def test_match_pairs_failed_when_time_runs_out(session):
    # every pair matched, no mistakes — but the clock beat the learner
    user_id, service = await _match_pairs_only(session, "m13@x.com", SIX_WORDS)
    await service.replenish(user_id)
    ex = await service.get_next(user_id)

    answers = {str(p["id"]): p["translation"] for p in ex.payload["pairs"]}
    result = await service.submit_attempt(
        user_id, ex.uuid, SubmitAttemptRequest(answers=answers, mistakes=0, timed_out=True)
    )

    assert result.is_correct is False
    assert result.result == AttemptResult.INCORRECT


async def test_match_pairs_failed_on_too_many_mistakes(session):
    user_id, service = await _match_pairs_only(session, "m5@x.com", SIX_WORDS)
    await service.replenish(user_id)
    ex = await service.get_next(user_id)

    answers = {str(p["id"]): p["translation"] for p in ex.payload["pairs"]}
    result = await service.submit_attempt(
        user_id,
        ex.uuid,
        SubmitAttemptRequest(answers=answers, mistakes=settings.exercises.MATCH_PAIRS_MAX_MISTAKES),
    )

    # even with every pair matched, blowing the mistake budget fails the round
    assert result.is_correct is False


async def test_match_pairs_leaves_unreached_words_untouched(session):
    # the round ended early: pairs the user never saw carry no signal
    user_id, service = await _match_pairs_only(session, "m6@x.com", SIX_WORDS)
    await service.replenish(user_id)
    ex = await service.get_next(user_id)

    pairs = ex.payload["pairs"]
    solved, untouched = pairs[0], pairs[-1]
    await service.submit_attempt(
        user_id,
        ex.uuid,
        SubmitAttemptRequest(answers={str(solved["id"]): solved["translation"]}, mistakes=3),
    )

    assert (await service.user_words.get_by_user_word(user_id, UUID(solved["word_uuid"]))).last_reviewed_at
    assert (await service.user_words.get_by_user_word(user_id, UUID(untouched["word_uuid"]))).last_reviewed_at is None


async def test_translations_are_cached_on_the_shared_word(session):
    user_id, service = await _match_pairs_only(session, "m7@x.com", SIX_WORDS)
    await service.replenish(user_id)
    calls_after_first = service.generator.calls

    # the cache lives on the shared Word row
    word = await service.words_repo.get_by_lemma_language("resilient", "en")
    assert word.definitions == [{"lang": "uk", "translation": "resilient-переклад"}]

    # a second round reuses it instead of paying for inference again
    await service.exercises.delete_by(user_id=user_id)
    await service.replenish(user_id)
    assert service.generator.calls == calls_after_first


async def test_flashcard_uses_a_cached_translation_without_calling_the_ai(session):
    # word/translation is the classic flashcard, and the translation is already
    # cached — so inference is saved for the types that genuinely need it
    user_id = await _seed_vocab(session, "f1@x.com", ["resilient"])
    service = ExercisePoolService(session, StubGenerator())
    word = await service.words_repo.get_by_lemma_language("resilient", "en")
    await service.words_repo.update_one(word, {"definitions": [{"lang": "uk", "translation": "стійкий"}]})

    await service.set_preferences(user_id, ExercisePreferences(exercise_types=[ExerciseType.FLASHCARD]))
    calls_before = service.generator.calls
    await service.replenish(user_id)

    assert service.generator.calls == calls_before  # no inference at all
    rows, _ = await service.exercises.get_many(user_id=user_id)
    card = next(r for r in rows if r.exercise_type == "FLASHCARD")
    assert card.payload == {"front": "resilient", "back": "стійкий", "example": None}


async def test_flashcard_falls_back_to_the_ai_without_a_translation(session):
    user_id = await _seed_vocab(session, "f2@x.com", ["resilient"])
    service = ExercisePoolService(session, StubGenerator())
    await service.set_preferences(user_id, ExercisePreferences(exercise_types=[ExerciseType.FLASHCARD]))

    await service.replenish(user_id)

    rows, _ = await service.exercises.get_many(user_id=user_id)
    card = next(r for r in rows if r.exercise_type == "FLASHCARD")
    assert card.payload["back"].startswith("true meaning")
    assert card.payload["example"]


# --- choosing exercise types -----------------------------------------------


async def test_all_types_enabled_by_default(session):
    user_id = await _seed_vocab(session, "p1@x.com", [])
    service = ExercisePoolService(session, StubGenerator())

    prefs = await service.get_preferences(user_id)
    assert set(prefs.exercise_types) == set(SUPPORTED_EXERCISE_TYPES)


async def test_preferences_round_trip(session):
    user_id = await _seed_vocab(session, "p2@x.com", [])
    service = ExercisePoolService(session, StubGenerator())

    await service.set_preferences(user_id, ExercisePreferences(exercise_types=[ExerciseType.FLASHCARD]))
    assert (await service.get_preferences(user_id)).exercise_types == [ExerciseType.FLASHCARD]


async def test_replenish_only_generates_enabled_types(session):
    user_id = await _seed_vocab(session, "p3@x.com", ["resilient", "eloquent", "serene"])
    service = ExercisePoolService(session, StubGenerator())
    await service.set_preferences(user_id, ExercisePreferences(exercise_types=[ExerciseType.FLASHCARD]))

    assert await service.replenish(user_id) == 3
    rows, _ = await service.exercises.get_many(user_id=user_id)
    assert {r.exercise_type for r in rows} == {"FLASHCARD"}


async def test_disabling_a_type_clears_it_from_the_pool(session):
    user_id = await _seed_vocab(session, "p4@x.com", ["resilient", "eloquent", "serene"])
    service = ExercisePoolService(session, StubGenerator())
    await service.replenish(user_id)  # one of each type
    assert await service.exercises.count_pending(user_id) == 3

    await service.set_preferences(user_id, ExercisePreferences(exercise_types=[ExerciseType.FLASHCARD]))

    rows, _ = await service.exercises.get_many(user_id=user_id)
    assert {r.exercise_type for r in rows} == {"FLASHCARD"}
    # the freed slots can be refilled again instead of being blocked
    assert await service.exercises.count_pending(user_id) == 1


async def test_disabling_a_type_keeps_an_already_served_exercise(session):
    # it is on the user's screen right now — dropping it would break the page
    user_id = await _seed_vocab(session, "p5@x.com", ["resilient"])
    service = ExercisePoolService(session, StubGenerator())
    await service.replenish(user_id)
    served = await service.get_next(user_id)

    await service.set_preferences(user_id, ExercisePreferences(exercise_types=[ExerciseType.FLASHCARD]))

    assert await service.exercises.get_for_user(user_id, served.uuid) is not None


async def test_preferences_reject_an_empty_list():
    with pytest.raises(ValidationError):
        ExercisePreferences(exercise_types=[])


async def test_preferences_reject_types_the_generator_cannot_produce():
    # accepting these would stall the pool: every generation attempt would fail
    with pytest.raises(ValidationError):
        ExercisePreferences(exercise_types=[ExerciseType.LISTENING])


async def test_stale_stored_preference_falls_back_to_defaults(session):
    # a type dropped from the supported set must not leave the user stuck
    user_id = await _seed_vocab(session, "p6@x.com", [])
    service = ExercisePoolService(session, StubGenerator())
    user = await service.users.get_by_id(user_id)
    await service.users.update_one(user, {"preferences": {"exercise_types": ["LISTENING"]}})

    assert set((await service.get_preferences(user_id)).exercise_types) == set(SUPPORTED_EXERCISE_TYPES)


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


async def test_get_next_can_filter_by_type(session):
    user_id = await _seed_vocab(session, "c2@x.com", ["resilient", "eloquent", "serene"])
    service = ExercisePoolService(session, StubGenerator())
    await service.replenish(user_id)  # one of each type

    ex = await service.get_next(user_id, ExerciseType.FLASHCARD)
    assert ex.exercise_type == ExerciseType.FLASHCARD

    # only one flashcard in the pool, and it is already served & unanswered ->
    # asking again re-serves the same one rather than a different type
    assert (await service.get_next(user_id, ExerciseType.FLASHCARD)).uuid == ex.uuid


async def test_get_next_filter_404s_when_that_type_is_absent(session):
    user_id = await _seed_vocab(session, "c3@x.com", ["resilient"])
    service = ExercisePoolService(session, StubGenerator())
    await service.set_preferences(user_id, ExercisePreferences(exercise_types=[ExerciseType.FILL_IN_BLANKS]))
    await service.replenish(user_id)

    with pytest.raises(ObjectNotFoundException):
        await service.get_next(user_id, ExerciseType.FLASHCARD)


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


async def _make_exercise(service, user_id, ex_type: ExerciseType, payload: dict, answer: dict):
    row = await service.exercises.create_one(
        {
            "user_id": user_id,
            "exercise_type": ex_type.value,
            "status": ExerciseStatus.READY.value,
            "payload": payload,
            "answer": answer,
            "is_ai_generated": True,
        }
    )
    return row.uuid


async def test_multiple_choice_grading(session):
    user_id = await _seed_vocab(session, "i@x.com", [])
    service = ExercisePoolService(session, StubGenerator())
    payload = {"word": "resilient", "options": ["wrong", "able to recover quickly", "also wrong"]}
    answer = {"1": "able to recover quickly"}

    ok_uuid = await _make_exercise(service, user_id, ExerciseType.MULTIPLE_CHOICE, payload, answer)
    result = await service.submit_attempt(
        user_id, ok_uuid, SubmitAttemptRequest(answers={"1": "able to recover quickly"})
    )
    assert result.is_correct is True

    bad_uuid = await _make_exercise(service, user_id, ExerciseType.MULTIPLE_CHOICE, payload, answer)
    result = await service.submit_attempt(user_id, bad_uuid, SubmitAttemptRequest(answers={"1": "wrong"}))
    assert result.is_correct is False
    assert result.correct_answers == answer


async def test_flashcard_self_grading(session):
    user_id = await _seed_vocab(session, "j@x.com", [])
    service = ExercisePoolService(session, StubGenerator())
    payload = {"front": "resilient", "back": "able to recover quickly", "example": None}
    answer = {"1": "know"}

    knew = await _make_exercise(service, user_id, ExerciseType.FLASHCARD, payload, answer)
    result = await service.submit_attempt(user_id, knew, SubmitAttemptRequest(answers={"1": "know"}))
    assert result.is_correct is True
    assert result.result == AttemptResult.CORRECT

    forgot = await _make_exercise(service, user_id, ExerciseType.FLASHCARD, payload, answer)
    result = await service.submit_attempt(user_id, forgot, SubmitAttemptRequest(answers={"1": "dont_know"}))
    assert result.is_correct is False


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


async def test_preferences_endpoints(app, client):
    headers = await _login(app, client)

    default = await client.get("/api/exercises/preferences", headers=headers)
    assert default.status_code == 200
    assert set(default.json()["exercise_types"]) == {t.value for t in SUPPORTED_EXERCISE_TYPES}

    saved = await client.put(
        "/api/exercises/preferences",
        json={"exercise_types": ["FLASHCARD", "MULTIPLE_CHOICE"]},
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["exercise_types"] == ["FLASHCARD", "MULTIPLE_CHOICE"]

    again = await client.get("/api/exercises/preferences", headers=headers)
    assert again.json()["exercise_types"] == ["FLASHCARD", "MULTIPLE_CHOICE"]


async def test_preferences_reject_empty_and_unknown_types(app, client):
    headers = await _login(app, client)
    assert (
        await client.put("/api/exercises/preferences", json={"exercise_types": []}, headers=headers)
    ).status_code == 422
    assert (
        await client.put("/api/exercises/preferences", json={"exercise_types": ["NOPE"]}, headers=headers)
    ).status_code == 422


async def test_preferences_require_auth(client):
    assert (await client.get("/api/exercises/preferences")).status_code == 401


async def test_refill_on_demand(app, client, sessionmaker):
    # answering everything must not leave the user stuck with an empty pool
    headers = await _login(app, client)
    await client.post("/api/vocabulary", json={"word": "resilient", "language": "en"}, headers=headers)

    async with sessionmaker() as s:
        # the endpoint must use a stubbed generator: refilling for real would
        # call the AI gateway
        app.dependency_overrides[get_exercise_pool_service] = lambda: ExercisePoolService(s, StubGenerator())

        empty = await client.get("/api/exercises/next", headers=headers)
        assert empty.status_code == 404

        refilled = await client.post("/api/exercises/refill", headers=headers)
        assert refilled.status_code == 200
        assert refilled.json()["created"] > 0

        assert (await client.get("/api/exercises/next", headers=headers)).status_code == 200
    app.dependency_overrides.pop(get_exercise_pool_service)


async def test_refill_requires_auth(client):
    assert (await client.post("/api/exercises/refill")).status_code == 401


async def test_refill_of_a_type_works_even_with_a_full_pool(session):
    # a pool full of other types is exactly when the learner cannot reach the
    # type they picked, so an explicit request must ignore the overall target
    user_id = await _seed_vocab(session, "r1@x.com", SIX_WORDS)
    service = ExercisePoolService(session, StubGenerator())
    await service.set_preferences(user_id, ExercisePreferences(exercise_types=[ExerciseType.MULTIPLE_CHOICE]))
    await service.replenish(user_id)
    assert await service.exercises.count_pending(user_id) >= settings.exercises.EXERCISE_POOL_TARGET

    created = await service.replenish(user_id, ExerciseType.FLASHCARD)

    assert created > 0
    assert await service.exercises.has_pending_of_type(user_id, "FLASHCARD")


async def test_refill_of_a_type_reuses_words_when_the_vocabulary_is_small(session):
    # one word must still produce the requested type — repeating a known word
    # is what practice is
    user_id = await _seed_vocab(session, "r2@x.com", ["resilient"])
    service = ExercisePoolService(session, StubGenerator())

    assert await service.replenish(user_id, ExerciseType.FLASHCARD) == 1
    assert await service.replenish(user_id, ExerciseType.FLASHCARD) == 1

    rows, _ = await service.exercises.get_many(user_id=user_id)
    assert len([r for r in rows if r.exercise_type == "FLASHCARD"]) == 2


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
