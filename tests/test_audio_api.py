"""Ф2: the audio endpoints — auth boundary, caching headers, and the miss path."""

import pytest

from app.core import settings
from app.services.audio.service import get_audio_service
from app.services.auth.oauth_google import get_google_verifier
from tests.test_audio_cache import FakeAI, FakeStorage

PROFILE = {"sub": "audio-sub-1", "email": "audio@gmail.com", "email_verified": True, "name": "Audio"}


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
def audio_app(app, sessionmaker):
    """Wire the real service and router to fake storage and a fake gateway."""
    storage, ai = FakeStorage(), FakeAI()

    async def _override():
        from app.repositories.audio_clip import AudioClipRepository
        from app.services.audio.service import AudioService

        async with sessionmaker() as s:
            yield AudioService(AudioClipRepository(s), storage, ai)

    app.dependency_overrides[get_audio_service] = _override
    app.dependency_overrides[get_google_verifier] = lambda: lambda _t: PROFILE
    app.state.fake_storage = storage
    app.state.fake_ai = ai
    return app


@pytest.fixture
async def headers(audio_app, client) -> dict[str, str]:
    token = (await client.post("/api/auth/google", json={"id_token": "fake"})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- POST /api/audio -------------------------------------------------------


async def test_post_requires_authentication(audio_app, client):
    """Synthesis costs CPU, so an anonymous caller must not be able to trigger it."""
    resp = await client.post("/api/audio", json={"text": "apple", "language": "en"})
    assert resp.status_code == 401
    assert audio_app.state.fake_ai.calls == []


async def test_post_returns_a_playable_url(audio_app, client, headers):
    resp = await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["url"] == f"/api/audio/{body['hash']}.mp3"
    assert body["voice"] == settings.audio.voice_map["en"]
    assert body["cached"] is False  # first time: it was synthesized
    assert body["duration_ms"] == 1000


async def test_post_reports_a_cache_hit_without_resynthesizing(audio_app, client, headers):
    payload = {"text": "apple", "language": "en"}
    first = await client.post("/api/audio", json=payload, headers=headers)
    second = await client.post("/api/audio", json=payload, headers=headers)
    assert first.json()["hash"] == second.json()["hash"]
    assert second.json()["cached"] is True
    assert len(audio_app.state.fake_ai.calls) == 1


async def test_post_rejects_oversized_text(audio_app, client, headers):
    resp = await client.post(
        "/api/audio",
        json={"text": "x" * (settings.audio.AUDIO_MAX_TEXT_LENGTH + 1), "language": "en"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert audio_app.state.fake_ai.calls == []


async def test_post_surfaces_a_dead_gateway_as_503(audio_app, client, headers, monkeypatch):
    async def boom(*a, **kw):
        raise RuntimeError("gateway down")

    monkeypatch.setattr(audio_app.state.fake_ai, "speak", boom)
    resp = await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)
    assert resp.status_code == 503


# --- GET /api/audio/{hash}.mp3 ---------------------------------------------


async def test_get_serves_the_mp3_without_authentication(audio_app, client, headers):
    """An <audio> element cannot send an Authorization header, so playback is open."""
    created = await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)
    hash_ = created.json()["hash"]

    resp = await client.get(f"/api/audio/{hash_}.mp3")  # no Authorization
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert resp.content.startswith(b"ID3")


async def test_get_is_cached_forever_by_the_browser(audio_app, client, headers):
    """The URL contains a hash of the audio, so it can never go stale."""
    created = await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)
    resp = await client.get(f"/api/audio/{created.json()['hash']}.mp3")
    cache_control = resp.headers["cache-control"]
    assert "immutable" in cache_control
    assert "max-age=31536000" in cache_control


async def _stored_clip(client, headers) -> tuple[str, bytes]:
    """A synthesized clip's hash and its full body, for the range tests below."""
    created = await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)
    hash_ = created.json()["hash"]
    body = (await client.get(f"/api/audio/{hash_}.mp3")).content
    return hash_, body


async def test_get_advertises_that_it_serves_ranges(audio_app, client, headers):
    """AVPlayer decides how to fetch from this header before it asks for anything."""
    hash_, _ = await _stored_clip(client, headers)
    resp = await client.get(f"/api/audio/{hash_}.mp3")
    assert resp.headers["accept-ranges"] == "bytes"


async def test_get_answers_a_byte_range_with_206(audio_app, client, headers):
    """iOS opens every clip with `bytes=0-1`; a plain 200 there is what broke playback."""
    hash_, full = await _stored_clip(client, headers)

    resp = await client.get(f"/api/audio/{hash_}.mp3", headers={"Range": "bytes=0-1"})
    assert resp.status_code == 206
    assert resp.content == full[:2]
    assert resp.headers["content-range"] == f"bytes 0-1/{len(full)}"
    assert resp.headers["content-length"] == "2"


async def test_get_serves_an_open_ended_range_to_the_end(audio_app, client, headers):
    hash_, full = await _stored_clip(client, headers)

    resp = await client.get(f"/api/audio/{hash_}.mp3", headers={"Range": "bytes=2-"})
    assert resp.status_code == 206
    assert resp.content == full[2:]
    assert resp.headers["content-range"] == f"bytes 2-{len(full) - 1}/{len(full)}"


async def test_get_serves_a_suffix_range(audio_app, client, headers):
    """`bytes=-N` means the LAST n bytes — a player reading trailing metadata."""
    hash_, full = await _stored_clip(client, headers)

    resp = await client.get(f"/api/audio/{hash_}.mp3", headers={"Range": "bytes=-3"})
    assert resp.status_code == 206
    assert resp.content == full[-3:]


async def test_get_falls_back_to_the_whole_clip_for_a_range_it_cannot_serve(audio_app, client, headers):
    """Answering in full is always valid, so an odd range must never be an error."""
    hash_, full = await _stored_clip(client, headers)

    for header in ("bytes=999999-", "bytes=0-1,4-5", "chunks=0-1", "nonsense"):
        resp = await client.get(f"/api/audio/{hash_}.mp3", headers={"Range": header})
        assert resp.status_code == 200, header
        assert resp.content == full, header


async def test_get_of_an_unknown_hash_is_404(audio_app, client):
    assert (await client.get(f"/api/audio/{'0' * 64}.mp3")).status_code == 404


async def test_get_after_storage_was_wiped_is_404_and_clears_the_row(audio_app, client, headers):
    created = await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)
    hash_ = created.json()["hash"]
    audio_app.state.fake_storage.objects.clear()

    assert (await client.get(f"/api/audio/{hash_}.mp3")).status_code == 404
    # the stale row is gone, so asking again re-synthesizes rather than 404-ing forever
    again = await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)
    assert again.json()["cached"] is False
    assert len(audio_app.state.fake_ai.calls) == 2
