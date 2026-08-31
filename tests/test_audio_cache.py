"""Ф1: the audio cache — key stability, storage, and the synth-once contract."""

import wave
from io import BytesIO

import pytest

from app.core import settings
from app.core.exc import BadRequestException, ServiceUnavailableException
from app.repositories.audio_clip import AudioClipRepository
from app.services.audio.keys import CACHE_VERSION, clip_hash, normalize_text, object_key
from app.services.audio.service import AudioService


def make_wav(seconds: float = 1.0, rate: int = 44100) -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x00\x00" * int(rate * seconds))
    return buffer.getvalue()


class FakeStorage:
    """In-memory stand-in for MinIO."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, content_type: str = "audio/mpeg") -> None:
        self.objects[key] = data

    async def get(self, key: str) -> bytes | None:
        return self.objects.get(key)

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class FakeAI:
    """Counts synthesis calls, so a cache hit is observable."""

    def __init__(self, voice: str = "M1") -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self.voice = voice

    async def speak(self, text: str, language: str, voice: str | None = None):
        self.calls.append((text, language, voice))
        return make_wav(), voice or self.voice


@pytest.fixture(autouse=True)
def _no_ffmpeg(monkeypatch):
    """Skip the real ffmpeg: transcoding and measuring are verified separately."""

    async def fake_encode(wav: bytes) -> bytes:
        return b"ID3" + wav[:64]

    async def fake_duration(mp3: bytes) -> int:
        return 1000

    monkeypatch.setattr("app.services.audio.service.transcode", fake_encode)
    monkeypatch.setattr("app.services.audio.service.clip_duration_ms", fake_duration)


@pytest.fixture
def audio(session):
    storage, ai = FakeStorage(), FakeAI()
    service = AudioService(AudioClipRepository(session), storage, ai)
    return service, storage, ai


# --- the cache key ---------------------------------------------------------


def test_hash_is_stable_across_calls():
    assert clip_hash("apple", "en", "M1") == clip_hash("apple", "en", "M1")


def test_hash_separates_language_and_voice():
    base = clip_hash("apple", "en", "M1")
    assert clip_hash("apple", "pl", "M1") != base  # same spelling, other language
    assert clip_hash("apple", "en", "F1") != base  # same words, other voice


def test_hash_ignores_incidental_whitespace():
    assert clip_hash("  the  apple ", "en", "M1") == clip_hash("the apple", "en", "M1")


def test_hash_keeps_case():
    """Capitalisation changes how a line is read, so it is not the same clip."""
    assert clip_hash("Polish", "en", "M1") != clip_hash("polish", "en", "M1")


def test_cache_version_participates_in_the_key():
    """Bumping the version must invalidate every existing clip."""
    import app.services.audio.keys as keys

    before = clip_hash("apple", "en", "M1")
    original = keys.CACHE_VERSION
    try:
        keys.CACHE_VERSION = "v2"
        assert clip_hash("apple", "en", "M1") != before
    finally:
        keys.CACHE_VERSION = original
    assert CACHE_VERSION == original


def test_object_key_is_sharded():
    hash_ = clip_hash("apple", "en", "M1")
    key = object_key(hash_)
    assert key == f"clips/{hash_[:2]}/{hash_}.mp3"


def test_normalize_text_collapses_runs():
    assert normalize_text("a\n b\t\tc ") == "a b c"


# --- the service -----------------------------------------------------------


async def test_first_request_synthesizes_and_stores(audio):
    service, storage, ai = audio
    clip, _ = await service.get_or_create("apple", "en")
    assert len(ai.calls) == 1
    assert clip.hash == clip_hash("apple", "en", "M1")
    assert clip.object_key in storage.objects
    assert clip.duration_ms == 1000
    assert clip.size_bytes == len(storage.objects[clip.object_key])


async def test_second_request_is_served_from_cache(audio):
    service, _, ai = audio
    first, _ = await service.get_or_create("apple", "en")
    second, _ = await service.get_or_create("apple", "en")
    assert len(ai.calls) == 1  # the gateway was not asked twice
    assert first.uuid == second.uuid


async def test_cache_is_shared_regardless_of_who_asks(audio):
    """The key covers what was said, not who asked — that is the whole point."""
    service, _, ai = audio
    await service.get_or_create("chorus line", "en")
    await service.get_or_create("chorus line", "en")
    await service.get_or_create("  chorus   line  ", "en")  # same words, sloppier
    assert len(ai.calls) == 1


async def test_an_explicit_voice_hits_the_cache_without_calling_the_gateway(audio):
    service, _, ai = audio
    await service.get_or_create("apple", "en", voice="F1")
    await service.get_or_create("apple", "en", voice="F1")
    assert len(ai.calls) == 1
    assert ai.calls[0][2] == "F1"


async def test_different_voices_are_different_clips(audio):
    service, _, ai = audio
    a, _ = await service.get_or_create("apple", "en", voice="M1")
    b, _ = await service.get_or_create("apple", "en", voice="F1")
    assert a.uuid != b.uuid
    assert len(ai.calls) == 2


async def test_voice_is_resolved_locally_from_the_language(audio):
    """The backend, not the gateway, decides the voice — otherwise the cache key
    is unknowable before synthesis and every unnamed request misses."""
    service, _, ai = audio
    clip, _ = await service.get_or_create("apple", "en")
    assert clip.voice == settings.audio.voice_map["en"]
    # the resolved voice is passed on, so the gateway never has to guess
    assert ai.calls[0][2] == settings.audio.voice_map["en"]


def test_resolve_voice_falls_back_for_an_unmapped_language():
    assert AudioService.resolve_voice("en") == settings.audio.voice_map["en"]
    assert AudioService.resolve_voice("en", "F4") == "F4"  # explicit wins
    assert AudioService.resolve_voice("zz") == settings.audio.AUDIO_FALLBACK_VOICE


async def test_read_returns_the_stored_bytes(audio):
    service, storage, _ = audio
    clip, _ = await service.get_or_create("apple", "en")
    data, row = await service.read(clip.hash)
    assert data == storage.objects[clip.object_key]
    assert row.uuid == clip.uuid


async def test_read_of_an_unknown_hash_is_none(audio):
    service, _, _ = audio
    assert await service.read("0" * 64) is None


async def test_a_row_whose_blob_vanished_is_dropped(audio):
    """Storage can be wiped independently; the next request must re-synthesize
    rather than 404 forever."""
    service, storage, _ = audio
    clip, _ = await service.get_or_create("apple", "en")
    storage.objects.clear()
    assert await service.read(clip.hash) is None
    assert await service.repo.get_by_hash(clip.hash) is None


async def test_empty_text_is_rejected(audio):
    service, _, _ = audio
    with pytest.raises(BadRequestException):
        await service.get_or_create("   ", "en")


async def test_oversized_text_is_rejected(audio):
    service, _, ai = audio
    with pytest.raises(BadRequestException):
        await service.get_or_create("x" * (settings.audio.AUDIO_MAX_TEXT_LENGTH + 1), "en")
    assert ai.calls == []  # rejected before reaching the gateway


async def test_a_dead_gateway_is_service_unavailable(audio, monkeypatch):
    service, _, ai = audio

    async def boom(*a, **kw):
        raise RuntimeError("gateway down")

    monkeypatch.setattr(ai, "speak", boom)
    with pytest.raises(ServiceUnavailableException):
        await service.get_or_create("apple", "en")


async def test_disabled_audio_is_service_unavailable(audio, monkeypatch):
    service, _, _ = audio
    monkeypatch.setattr(settings.audio, "AUDIO_ENABLED", False)
    with pytest.raises(ServiceUnavailableException):
        await service.get_or_create("apple", "en")
