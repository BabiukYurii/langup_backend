"""Ф6: choosing a voice, and the preferences blob that stores it."""

import pytest

from app.core import settings
from app.services.audio.keys import VOICE_PREF_KEY
from app.services.audio.service import get_audio_service
from app.services.auth.oauth_google import get_google_verifier
from tests.test_audio_cache import FakeAI, FakeStorage

PROFILE = {"sub": "voice-sub-1", "email": "voice@gmail.com", "email_verified": True, "name": "Voice"}


@pytest.fixture(autouse=True)
def _no_ffmpeg(monkeypatch):
    async def fake_encode(wav: bytes) -> bytes:
        return b"ID3" + wav[:64]

    async def fake_duration(mp3: bytes) -> int:
        return 1000

    monkeypatch.setattr("app.services.audio.service.wav_to_mp3", fake_encode)
    monkeypatch.setattr("app.services.audio.service.mp3_duration_ms", fake_duration)


@pytest.fixture
def voice_app(app, sessionmaker):
    storage, ai = FakeStorage(), FakeAI()

    async def _override():
        from app.repositories.audio_clip import AudioClipRepository
        from app.services.audio.service import AudioService

        async with sessionmaker() as s:
            yield AudioService(AudioClipRepository(s), storage, ai)

    app.dependency_overrides[get_audio_service] = _override
    app.dependency_overrides[get_google_verifier] = lambda: lambda _t: PROFILE
    app.state.fake_ai = ai
    return app


@pytest.fixture
async def session_info(voice_app, client):
    body = (await client.post("/api/auth/google", json={"id_token": "fake"})).json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    me = (await client.get("/api/auth/me", headers=headers)).json()
    return headers, me["id"]


async def set_voice(client, headers, user_id, voice):
    return await client.patch(f"/api/users/{user_id}", json={"preferences": {VOICE_PREF_KEY: voice}}, headers=headers)


# --- the roster ------------------------------------------------------------


async def test_voices_endpoint_lists_the_roster(voice_app, client, session_info):
    headers, _ = session_info
    body = (await client.get("/api/audio/voices", headers=headers)).json()
    assert body["voices"] == settings.audio.available_voices
    assert body["selected"] is None  # nothing chosen yet
    assert body["defaults"]["en"] == settings.audio.voice_map["en"]


async def test_voices_endpoint_requires_authentication(voice_app, client):
    assert (await client.get("/api/audio/voices")).status_code == 401


# --- the preference is applied --------------------------------------------


async def test_saved_voice_is_used_when_none_is_requested(voice_app, client, session_info):
    headers, user_id = session_info
    await set_voice(client, headers, user_id, "F4")

    body = (await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)).json()
    assert body["voice"] == "F4"  # not the "en" default
    assert (await client.get("/api/audio/voices", headers=headers)).json()["selected"] == "F4"


async def test_an_explicit_voice_still_wins(voice_app, client, session_info):
    """The picker previews a voice before it is saved, so the request must win."""
    headers, user_id = session_info
    await set_voice(client, headers, user_id, "F4")

    body = (
        await client.post("/api/audio", json={"text": "apple", "language": "en", "voice": "M2"}, headers=headers)
    ).json()
    assert body["voice"] == "M2"


async def test_an_unknown_saved_voice_is_ignored(voice_app, client, session_info):
    """A stale or hand-edited preference must not send junk to the engine."""
    headers, user_id = session_info
    await set_voice(client, headers, user_id, "NOT-A-VOICE")

    body = (await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)).json()
    assert body["voice"] == settings.audio.voice_map["en"]


async def test_clearing_the_voice_returns_to_the_language_default(voice_app, client, session_info):
    headers, user_id = session_info
    await set_voice(client, headers, user_id, "F4")
    await set_voice(client, headers, user_id, None)

    body = (await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)).json()
    assert body["voice"] == settings.audio.voice_map["en"]


# --- the shared preferences blob ------------------------------------------


async def test_updating_one_preference_keeps_the_others(voice_app, client, session_info):
    """preferences is written by several independent screens. A PATCH naming one
    key must not wipe what the exercise settings put there."""
    headers, user_id = session_info
    await client.patch(
        f"/api/users/{user_id}",
        json={"preferences": {"exercise_types": ["TYPING"], "match_pairs_fillers": False}},
        headers=headers,
    )
    await set_voice(client, headers, user_id, "M3")

    prefs = (await client.get("/api/auth/me", headers=headers)).json()["preferences"]
    assert prefs[VOICE_PREF_KEY] == "M3"
    assert prefs["exercise_types"] == ["TYPING"]  # untouched
    assert prefs["match_pairs_fillers"] is False


async def test_other_profile_fields_do_not_disturb_preferences(voice_app, client, session_info):
    headers, user_id = session_info
    await set_voice(client, headers, user_id, "M3")
    await client.patch(f"/api/users/{user_id}", json={"full_name": "Renamed"}, headers=headers)

    me = (await client.get("/api/auth/me", headers=headers)).json()
    assert me["full_name"] == "Renamed"
    assert me["preferences"][VOICE_PREF_KEY] == "M3"
