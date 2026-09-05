"""Ф4 of the playlist warm-up: preparing one song without getting in the way.

The two properties worth defending here are that the work is FINDABLE (the key
it writes is the key a tap reads) and that it is POLITE (it stops the moment a
learner needs the model, and loses nothing by stopping).
"""

from uuid import uuid4

import pytest

from app.celery.tasks import warm_tasks
from app.repositories.word_translation import WordTranslationRepository
from app.schemas.ai import GeneratedTranslation
from app.services.songs.analysis import analyze_lyrics
from app.services.songs.warm_scheduler import WarmCandidate

LYRICS = "Wandering lonely tonight\nThe wandering shadows return"


class _CountingGen:
    def __init__(self) -> None:
        self.words: list[str] = []

    async def generate_translation(self, params):
        self.words.append(params.word)
        return GeneratedTranslation(translation=f"gloss:{params.word}", model="stub")


def _candidate() -> WarmCandidate:
    return WarmCandidate(
        song_uuid=uuid4(),
        source_language="en",
        target_language="uk",
        position=0,
        title="Wandering",
        artist="Nobody",
    )


@pytest.fixture(autouse=True)
def _quiet_model(monkeypatch):
    """Nobody is waiting on the model unless a test says otherwise."""

    async def not_busy():
        return False

    monkeypatch.setattr("app.services.learning.model_busy.model_is_busy", not_busy)


@pytest.fixture(autouse=True)
def _lyrics(monkeypatch):
    async def fetch(title, artist):
        return LYRICS

    monkeypatch.setattr("app.services.lyrics.fetch_lyrics", fetch)


# --- the key has to match what a tap looks up ------------------------------


def test_the_line_is_rebuilt_exactly_as_the_reader_builds_it():
    """The client sends tokens.map(surface).join() — no separator, punctuation
    included. Any other reconstruction and the whole night's work is invisible."""
    analyzed = analyze_lyrics(LYRICS, "en", set(), set())
    lines = {line for _, line in warm_tasks.context_lines(analyzed)}
    assert "Wandering lonely tonight" in lines


def test_words_come_in_reading_order():
    """Half a warmed song should be instant where a learner starts, not
    uniformly half-ready."""
    analyzed = analyze_lyrics(LYRICS, "en", set(), set())
    words = [w.lower() for w, _ in warm_tasks.context_lines(analyzed)]
    assert words.index("wandering") < words.index("shadows")


def test_a_repeated_word_in_the_same_line_is_asked_once():
    analyzed = analyze_lyrics("echo echo echo", "en", set(), set())
    assert len(warm_tasks.context_lines(analyzed)) == 1


def test_the_same_word_in_a_different_line_is_a_separate_question():
    """Context is the point of the feature: two lines can mean two senses."""
    analyzed = analyze_lyrics(LYRICS, "en", set(), set())
    wandering = [line for word, line in warm_tasks.context_lines(analyzed) if word.lower() == "wandering"]
    assert len(wandering) == 2


# --- warming ---------------------------------------------------------------


async def test_a_warmed_song_is_complete_and_stored(sessionmaker):
    gen = _CountingGen()
    async with sessionmaker() as session:
        result = await warm_tasks.warm_song(session, _candidate(), gen)

        assert result.completed is True
        assert result.reason == "done"
        assert result.words_translated == len(gen.words) > 0

        cached = await WordTranslationRepository(session).get_cached("lonely", "en", "uk", "Wandering lonely tonight")
        assert cached == "gloss:lonely"


async def test_a_learner_tapping_that_word_now_pays_nothing(sessionmaker):
    """The point of the whole feature, asserted end to end."""
    from app.services.songs.service import SongService

    warm_gen, tap_gen = _CountingGen(), _CountingGen()
    async with sessionmaker() as session:
        await warm_tasks.warm_song(session, _candidate(), warm_gen)

        service = SongService(session, tap_gen)
        service.translations = WordTranslationRepository(session)

        async def _uk(s, u):
            return "uk"

        import app.services.learning.exercise_service as ex

        original, ex.translation_language_for = ex.translation_language_for, _uk
        try:
            answer = await service.translate_in_context(1, "lonely", "Wandering lonely tonight", "en")
        finally:
            ex.translation_language_for = original

    assert answer == "gloss:lonely"
    assert tap_gen.words == []  # the model was never asked


async def test_a_second_run_does_nothing(sessionmaker):
    """The cache is the cursor: repeating a run must be free."""
    async with sessionmaker() as session:
        await warm_tasks.warm_song(session, _candidate(), _CountingGen())
        second = _CountingGen()
        result = await warm_tasks.warm_song(session, _candidate(), second)

    assert second.words == []
    assert result.completed is True


# --- yielding --------------------------------------------------------------


async def test_it_stands_aside_when_a_learner_is_waiting(sessionmaker, monkeypatch):
    async def busy():
        return True

    monkeypatch.setattr("app.services.learning.model_busy.model_is_busy", busy)
    gen = _CountingGen()
    async with sessionmaker() as session:
        result = await warm_tasks.warm_song(session, _candidate(), gen)

    assert gen.words == []
    assert result.reason == "yielded"
    assert result.completed is False  # so the pair is picked up again later


async def test_the_word_cap_stops_one_song_taking_the_night(sessionmaker):
    gen = _CountingGen()
    async with sessionmaker() as session:
        result = await warm_tasks.warm_song(session, _candidate(), gen, word_cap=1)

    assert len(gen.words) == 1
    assert result.reason == "capped"
    assert result.completed is False


async def test_the_budget_stops_a_run_short(sessionmaker):
    gen = _CountingGen()
    async with sessionmaker() as session:
        result = await warm_tasks.warm_song(session, _candidate(), gen, budget_seconds=0)

    assert gen.words == []
    assert result.reason == "budget"


async def test_an_interrupted_run_keeps_what_it_finished(sessionmaker):
    """Stopping early must cost only the fetch, never the words already done."""
    async with sessionmaker() as session:
        first = _CountingGen()
        await warm_tasks.warm_song(session, _candidate(), first, word_cap=1)

        second = _CountingGen()
        result = await warm_tasks.warm_song(session, _candidate(), second)

        assert first.words[0] not in second.words  # not redone
        assert result.completed is True


# --- degrading -------------------------------------------------------------


async def test_missing_lyrics_leaves_the_pair_open(sessionmaker, monkeypatch):
    """lyrics_found said yes, so an empty fetch is a hiccup, not a verdict."""

    async def nothing(title, artist):
        return None

    monkeypatch.setattr("app.services.lyrics.fetch_lyrics", nothing)
    async with sessionmaker() as session:
        result = await warm_tasks.warm_song(session, _candidate(), _CountingGen())

    assert result.reason == "no_lyrics"
    assert result.completed is False


async def test_a_word_the_model_refuses_does_not_fail_the_song(sessionmaker):
    from app.core.exc import AIProviderError

    class _OneBadWord(_CountingGen):
        async def generate_translation(self, params):
            if params.word.lower() == "lonely":
                raise AIProviderError("gateway down")
            return await super().generate_translation(params)

    async with sessionmaker() as session:
        result = await warm_tasks.warm_song(session, _candidate(), _OneBadWord())

    assert result.words_translated > 0
    assert result.completed is False  # left open, so the word is retried later


# --- audio shares the gateway, so it is throttled too ----------------------


async def test_a_word_in_many_lines_is_spoken_once(sessionmaker):
    """A clip is keyed by (text, language, voice) and knows nothing about lines,
    so repeating the word only repeats the lookup."""
    spoken: list[str] = []

    async def fake_audio(words, language, voice):
        spoken.extend(words)
        return len(words)

    async with sessionmaker() as session:
        await warm_tasks.warm_song(session, _candidate(), _CountingGen(), warm_audio=fake_audio)

    # Exact strings, not case-folded: clip_hash keeps case on purpose, so
    # "Wandering" opening a line really is a different clip from "wandering".
    assert len(spoken) == len(set(spoken))
    assert any(w.lower() == "wandering" for w in spoken)  # and it is in there


async def test_audio_stops_when_a_learner_starts_waiting(sessionmaker, monkeypatch):
    """Synthesis is not inference, but it goes to the same gateway on the same
    machine — so it must yield like everything else."""
    calls = {"n": 0}

    async def fake_audio(words, language, voice):
        calls["n"] += 1
        return len(words)

    async def busy():
        return True

    async with sessionmaker() as session:
        # Translate first while the gateway is free, then have a learner arrive.
        await warm_tasks.warm_song(session, _candidate(), _CountingGen())
        monkeypatch.setattr("app.services.learning.model_busy.model_is_busy", busy)
        result = await warm_tasks.warm_song(session, _candidate(), _CountingGen(), warm_audio=fake_audio)

    assert calls["n"] == 0
    assert result.clips_warmed == 0
