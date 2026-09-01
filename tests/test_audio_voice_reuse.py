"""Changing voice: hearing the new one, and collecting what nobody wants."""

import pytest

from app.core import settings
from app.models import User
from app.services.audio.keys import LEGACY_VOICE_PREF_KEY, VOICES_PREF_KEY, clip_hash
from app.services.audio.usage import voices_in_use
from tests.test_audio_cache import FakeAI
from tests.test_audio_orphans import ListableStorage  # noqa: F401 — fixture support


@pytest.fixture(autouse=True)
def _no_ffmpeg(monkeypatch):
    async def fake_encode(wav: bytes) -> bytes:
        return b"ID3" + wav[:64]

    async def fake_duration(mp3: bytes) -> int:
        return 1000

    monkeypatch.setattr("app.services.audio.service.transcode", fake_encode)
    monkeypatch.setattr("app.services.audio.service.clip_duration_ms", fake_duration)


@pytest.fixture
def audio(session):
    from app.repositories.audio_clip import AudioClipRepository
    from app.services.audio.service import AudioService

    storage, ai = ListableStorage(), FakeAI()
    return AudioService(AudioClipRepository(session), storage, ai), storage


async def add_user(session, prefs, email):
    user = User(email=email, hashed_password="x", preferences=prefs)
    session.add(user)
    await session.commit()
    return user


# --- re-voicing needs no special machinery ---------------------------------


async def test_a_new_voice_produces_a_new_clip(audio):
    """The voice is part of the cache key, so switching simply misses and
    re-synthesizes — nothing has to invalidate anything."""
    service, _ = audio
    old, _ = await service.get_or_create("apple", "en", "M1")
    new, cached = await service.get_or_create("apple", "en", "F3")
    assert new.hash != old.hash
    assert cached is False  # actually spoken again, not served from the old one
    assert new.voice == "F3"


def test_the_key_separates_voices():
    assert clip_hash("apple", "en", "M1") != clip_hash("apple", "en", "F3")


# --- who still uses which voice --------------------------------------------


async def test_configured_defaults_always_count_as_in_use(session):
    """Most learners have chosen nothing, so the defaults are what they hear."""
    in_use = await voices_in_use(session)
    assert ("en", settings.audio.voice_map["en"]) in in_use


async def test_a_learners_choice_counts(session):
    await add_user(session, {VOICES_PREF_KEY: {"en": "F4"}}, "a@x.com")
    assert ("en", "F4") in await voices_in_use(session)


async def test_the_old_single_key_counts_for_every_language(session):
    """It is still honoured at request time, so it must be honoured here too —
    otherwise the sweep would delete clips that are actively served."""
    await add_user(session, {LEGACY_VOICE_PREF_KEY: "M5"}, "b@x.com")
    in_use = await voices_in_use(session)
    assert ("en", "M5") in in_use
    assert ("pl", "M5") in in_use


async def test_a_junk_preference_does_not_widen_the_set(session):
    await add_user(session, {VOICES_PREF_KEY: {"en": "NOT-A-VOICE"}}, "c@x.com")
    assert ("en", "NOT-A-VOICE") not in await voices_in_use(session)


# --- sweeping what nobody uses ---------------------------------------------


async def test_a_voice_nobody_uses_is_collected(audio, session):
    service, storage = audio
    clip, _ = await service.get_or_create("apple", "en", "F4")

    in_use = await voices_in_use(session)  # F4 chosen by nobody
    unused, removed = await service.sweep_unused_voices(in_use, delete=True)
    assert unused == [clip.hash]
    assert removed == 1
    assert clip.object_key not in storage.objects


async def test_a_voice_someone_else_still_uses_is_kept(audio, session):
    """The cache is shared, so one learner switching away says nothing about
    the rest — this is the case that must never delete."""
    service, storage = audio
    clip, _ = await service.get_or_create("apple", "en", "F4")
    await add_user(session, {VOICES_PREF_KEY: {"en": "F4"}}, "keeper@x.com")

    unused, removed = await service.sweep_unused_voices(await voices_in_use(session), delete=True)
    assert unused == []
    assert removed == 0
    assert clip.object_key in storage.objects


async def test_the_language_default_is_never_collected(audio, session):
    service, _ = audio
    await service.get_or_create("apple", "en")  # resolves to the default voice
    unused, _ = await service.sweep_unused_voices(await voices_in_use(session))
    assert unused == []


async def test_the_same_voice_in_another_language_is_not_a_reason_to_keep(audio, session):
    """Usage is per (language, voice): choosing F4 for Polish does not make an
    English F4 clip wanted."""
    service, _ = audio
    clip, _ = await service.get_or_create("apple", "en", "F4")
    await add_user(session, {VOICES_PREF_KEY: {"pl": "F4"}}, "pl@x.com")

    unused, _ = await service.sweep_unused_voices(await voices_in_use(session))
    assert unused == [clip.hash]


async def test_demo_phrases_are_spared(audio, session):
    """The picker offers all ten voices to everyone, so its clips are in use by
    definition even though nobody has chosen those voices."""
    service, _ = audio
    phrase = "Hi! I am the voice that will read your words."
    clip, _ = await service.get_or_create(phrase, "en", "F4")

    unused, removed = await service.sweep_unused_voices(
        await voices_in_use(session), exempt_texts={phrase}, delete=True
    )
    assert unused == []
    assert await service.repo.get_by_hash(clip.hash) is not None


async def test_reporting_does_not_delete(audio, session):
    service, storage = audio
    clip, _ = await service.get_or_create("apple", "en", "F4")
    await service.sweep_unused_voices(await voices_in_use(session))
    assert clip.object_key in storage.objects
