"""Ф7: warming the cache so the first tap is not the slow one."""

import pytest

from app.celery.tasks import audio_tasks
from app.core import settings


@pytest.fixture
def warm(monkeypatch, session):
    """Run warm_clips against the test session and a fake service."""
    calls: list[tuple[str, str, str | None]] = []

    class FakeService:
        def __init__(self, *a, **kw) -> None:
            pass

        async def get_or_create(self, text, language, voice=None):
            calls.append((text, language, voice))
            return object(), False

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_session():
        yield session

    monkeypatch.setattr(audio_tasks, "_session", fake_session)
    monkeypatch.setattr("app.services.audio.service.AudioService", FakeService)
    return calls


async def test_warms_each_text(warm):
    warmed = await audio_tasks.warm_clips(["apple", "She ate an apple."], "en")
    assert warmed == 2
    assert [c[0] for c in warm] == ["apple", "She ate an apple."]


async def test_passes_the_chosen_voice_through(warm):
    """A warmed clip must match the voice the learner will actually hear, or it
    is cached under a key nobody looks up."""
    await audio_tasks.warm_clips(["apple"], "en", "F4")
    assert warm[0] == ("apple", "en", "F4")


async def test_blank_texts_are_skipped(warm):
    assert await audio_tasks.warm_clips(["", "   ", "apple"], "en") == 1


async def test_texts_over_the_cap_are_skipped(warm):
    """A captured sentence may be 2000 chars; the audio cap is 400. That is a
    predictable case, not something to log a warning about."""
    long_sentence = "x" * (settings.audio.AUDIO_MAX_TEXT_LENGTH + 1)
    assert await audio_tasks.warm_clips([long_sentence, "apple"], "en") == 1
    assert [c[0] for c in warm] == ["apple"]


async def test_a_failure_never_escalates(warm, monkeypatch):
    """Warming is optional — a busy gateway must not fail anything."""

    class Boom:
        def __init__(self, *a, **kw) -> None:
            pass

        async def get_or_create(self, *a, **kw):
            raise RuntimeError("gateway down")

    monkeypatch.setattr("app.services.audio.service.AudioService", Boom)
    assert await audio_tasks.warm_clips(["apple"], "en") == 0


async def test_disabled_audio_warms_nothing(warm, monkeypatch):
    monkeypatch.setattr(settings.audio, "AUDIO_ENABLED", False)
    assert await audio_tasks.warm_clips(["apple"], "en") == 0
    assert warm == []
