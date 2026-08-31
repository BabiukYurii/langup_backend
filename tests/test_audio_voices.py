"""Ф6: choosing a voice, and the preferences blob that stores it."""

import pytest

from app.core import settings
from app.services.audio.keys import LEGACY_VOICE_PREF_KEY, VOICES_PREF_KEY
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


async def set_voices(client, headers, user_id, mapping):
    return await client.patch(
        f"/api/users/{user_id}", json={"preferences": {VOICES_PREF_KEY: mapping}}, headers=headers
    )


# --- the roster ------------------------------------------------------------


async def test_voices_endpoint_lists_the_roster(voice_app, client, session_info):
    headers, _ = session_info
    body = (await client.get("/api/audio/voices", headers=headers)).json()
    assert body["voices"] == settings.audio.available_voices
    assert body["selected"] == {}  # nothing chosen yet
    assert body["defaults"]["en"] == settings.audio.voice_map["en"]


async def test_voices_endpoint_requires_authentication(voice_app, client):
    assert (await client.get("/api/audio/voices")).status_code == 401


# --- the preference is applied --------------------------------------------


async def test_saved_voice_is_used_when_none_is_requested(voice_app, client, session_info):
    headers, user_id = session_info
    await set_voices(client, headers, user_id, {"en": "F4"})

    body = (await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)).json()
    assert body["voice"] == "F4"  # not the "en" default
    assert (await client.get("/api/audio/voices", headers=headers)).json()["selected"] == {"en": "F4"}


async def test_each_language_keeps_its_own_voice(voice_app, client, session_info):
    """The whole point of the map: a learner studying two languages hears two
    different voices, and choosing one must not change the other."""
    headers, user_id = session_info
    await set_voices(client, headers, user_id, {"en": "M2", "pl": "F3"})

    en = (await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)).json()
    pl = (await client.post("/api/audio", json={"text": "jablko", "language": "pl"}, headers=headers)).json()
    assert (en["voice"], pl["voice"]) == ("M2", "F3")


async def test_a_language_without_a_choice_falls_back(voice_app, client, session_info):
    """Choosing a voice for one language must not silently apply to the rest."""
    headers, user_id = session_info
    await set_voices(client, headers, user_id, {"en": "M2"})

    body = (await client.post("/api/audio", json={"text": "jablko", "language": "pl"}, headers=headers)).json()
    assert body["voice"] == settings.audio.voice_map["pl"]


async def test_an_explicit_voice_still_wins(voice_app, client, session_info):
    """The picker previews a voice before it is saved, so the request must win."""
    headers, user_id = session_info
    await set_voices(client, headers, user_id, {"en": "F4"})

    body = (
        await client.post("/api/audio", json={"text": "apple", "language": "en", "voice": "M2"}, headers=headers)
    ).json()
    assert body["voice"] == "M2"


async def test_an_unknown_saved_voice_is_ignored(voice_app, client, session_info):
    """A stale or hand-edited preference must not send junk to the engine."""
    headers, user_id = session_info
    await set_voices(client, headers, user_id, {"en": "NOT-A-VOICE"})

    body = (await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)).json()
    assert body["voice"] == settings.audio.voice_map["en"]


async def test_clearing_the_voice_returns_to_the_language_default(voice_app, client, session_info):
    headers, user_id = session_info
    await set_voices(client, headers, user_id, {"en": "F4"})
    await set_voices(client, headers, user_id, {})

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
    await set_voices(client, headers, user_id, {"en": "M3"})

    prefs = (await client.get("/api/auth/me", headers=headers)).json()["preferences"]
    assert prefs[VOICES_PREF_KEY] == {"en": "M3"}
    assert prefs["exercise_types"] == ["TYPING"]  # untouched
    assert prefs["match_pairs_fillers"] is False


async def test_other_profile_fields_do_not_disturb_preferences(voice_app, client, session_info):
    headers, user_id = session_info
    await set_voices(client, headers, user_id, {"en": "M3"})
    await client.patch(f"/api/users/{user_id}", json={"full_name": "Renamed"}, headers=headers)

    me = (await client.get("/api/auth/me", headers=headers)).json()
    assert me["full_name"] == "Renamed"
    assert me["preferences"][VOICES_PREF_KEY] == {"en": "M3"}


async def test_a_voice_saved_by_the_old_single_key_still_applies(voice_app, client, session_info):
    """The first cut stored one voice for the account. An existing choice must
    keep working until a per-language one replaces it."""
    headers, user_id = session_info
    await client.patch(f"/api/users/{user_id}", json={"preferences": {LEGACY_VOICE_PREF_KEY: "M5"}}, headers=headers)

    body = (await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)).json()
    assert body["voice"] == "M5"


async def test_a_per_language_choice_overrides_the_old_key(voice_app, client, session_info):
    headers, user_id = session_info
    await client.patch(f"/api/users/{user_id}", json={"preferences": {LEGACY_VOICE_PREF_KEY: "M5"}}, headers=headers)
    await set_voices(client, headers, user_id, {"en": "F2"})

    body = (await client.post("/api/audio", json={"text": "apple", "language": "en"}, headers=headers)).json()
    assert body["voice"] == "F2"
