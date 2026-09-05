"""Ф1 of the playlist warm-up: song word translations are cached and shared.

The cache is what makes warming worth doing at all — without it there is nowhere
to put work done ahead of time. It is keyed by the word, its context and the two
languages, never by the user, so a gloss paid for once serves everyone.
"""

import pytest

from app.core.exc import AIProviderError
from app.repositories.word_translation import WordTranslationRepository
from app.schemas.ai import GeneratedTranslation
from app.services.songs.service import SongService
from app.services.songs.translation_keys import context_hash

pytestmark = pytest.mark.asyncio


class _CountingGen:
    """Counts model calls, so a cache hit is provable rather than assumed."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def generate_translation(self, params):
        self.calls.append((params.word, params.sentence, params.source_language, params.target_language))
        return GeneratedTranslation(translation=f"gloss:{params.word}", model="stub")


class _FailGen:
    async def generate_translation(self, params):
        raise AIProviderError("gateway down")


@pytest.fixture
def target_uk(monkeypatch):
    """Pin the learner's translation language; who they are is not the subject."""

    async def _target(session, user_id):
        return "uk"

    monkeypatch.setattr("app.services.learning.exercise_service.translation_language_for", _target)


# --- read-through ----------------------------------------------------------


async def test_second_ask_is_served_from_cache(sessionmaker, target_uk):
    gen = _CountingGen()
    async with sessionmaker() as session:
        service = SongService(session, gen)
        first = await service.translate_in_context(1, "asleep", "Fall asleep tonight", "en")
        second = await service.translate_in_context(1, "asleep", "Fall asleep tonight", "en")

    assert first == second == "gloss:asleep"
    assert len(gen.calls) == 1  # the model was asked once, not twice


async def test_another_learner_reads_the_first_ones_answer(sessionmaker, target_uk):
    """The row is keyed by the question, not the asker — that is what makes
    warming a whole playlist affordable."""
    gen = _CountingGen()
    async with sessionmaker() as session:
        service = SongService(session, gen)
        await service.translate_in_context(1, "asleep", "Fall asleep tonight", "en")
        other = await service.translate_in_context(999, "asleep", "Fall asleep tonight", "en")

    assert other == "gloss:asleep"
    assert len(gen.calls) == 1


async def test_a_different_line_is_translated_again(sessionmaker, target_uk):
    gen = _CountingGen()
    async with sessionmaker() as session:
        service = SongService(session, gen)
        await service.translate_in_context(1, "fall", "Fall asleep tonight", "en")
        await service.translate_in_context(1, "fall", "A fall from grace", "en")

    assert len(gen.calls) == 2  # same word, different sense


async def test_a_failed_translation_is_not_cached(sessionmaker, target_uk):
    """A gateway blip must not poison the cache with a permanent None."""
    async with sessionmaker() as session:
        service = SongService(session, _FailGen())
        assert await service.translate_in_context(1, "asleep", "Fall asleep tonight", "en") is None

        gen = _CountingGen()
        service = SongService(session, gen)
        assert await service.translate_in_context(1, "asleep", "Fall asleep tonight", "en") == "gloss:asleep"
        assert len(gen.calls) == 1  # asked again, rather than serving the failure


async def test_the_song_line_is_never_stored(sessionmaker, target_uk):
    """The lyrics are parsed fresh every time and kept nowhere; the cache holds
    a hash of the line, so it cannot quietly become a copy of the song."""
    line = "Fall asleep tonight"
    async with sessionmaker() as session:
        service = SongService(session, _CountingGen())
        await service.translate_in_context(1, "asleep", line, "en")

        rows, total = await WordTranslationRepository(session).get_many()
        assert total == 1
        stored = " ".join(str(v) for v in rows[0].__dict__.values() if isinstance(v, str))
        assert line.lower() not in stored.lower()
        assert rows[0].context_hash == context_hash(line)


async def test_a_concurrent_write_does_not_raise(sessionmaker, target_uk):
    """Two learners can tap the same word in the same second, and the warmer can
    be filling a song someone is already reading."""
    async with sessionmaker() as session:
        repo = WordTranslationRepository(session)
        await repo.remember("asleep", "en", "uk", "Fall asleep tonight", "first")
        await repo.remember("asleep", "en", "uk", "Fall asleep tonight", "second")

        assert await repo.get_cached("asleep", "en", "uk", "Fall asleep tonight") == "first"
