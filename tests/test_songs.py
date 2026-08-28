import pytest

from app.models import UserWord, Word
from app.schemas.ai import GeneratedTranslation
from app.services.ai.exercise_generation import get_exercise_generation_service
from app.services.auth.oauth_google import get_google_verifier
from app.services.songs import service as song_service

pytestmark = pytest.mark.asyncio

PROFILE = {"sub": "song-sub-1", "email": "song@gmail.com", "email_verified": True, "name": "Song"}

EN_LYRICS = "The cat and the dog run in the park every morning together\nThe cat is happy today"


async def _login(app, client) -> dict:
    app.dependency_overrides[get_google_verifier] = lambda: lambda _t: PROFILE
    token = (await client.post("/api/auth/google", json={"id_token": "fake"})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _patch_lyrics(monkeypatch, text):
    async def fake(title, artist):
        return text

    monkeypatch.setattr(song_service, "fetch_lyrics", fake)


async def test_analyze_song_marks_known_and_unknown(app, client, session, monkeypatch):
    headers = await _login(app, client)
    me = (await client.get("/api/auth/me", headers=headers)).json()
    word = Word(lemma="cat", language="en")
    session.add(word)
    await session.flush()
    # mastered -> should render as "known" (green), not "learning"
    session.add(UserWord(user_id=me["id"], word_uuid=word.uuid, mastery_level="MASTERED"))
    await session.commit()  # commit: request opens its own session on the shared connection

    _patch_lyrics(monkeypatch, EN_LYRICS)
    resp = await client.post("/api/playlists/song/analyze", json={"title": "t", "artist": "a"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["language"] == "en"
    status = {t["surface"]: t["status"] for line in body["lines"] for t in line["tokens"]}
    assert status["cat"] == "known"
    assert status["dog"] == "unknown"
    assert status["The"] == "skip"  # stopword
    assert "dog" in {u["lemma"] for u in body["unknown"]}


async def test_analyze_song_lyrics_not_found(app, client, monkeypatch):
    headers = await _login(app, client)
    _patch_lyrics(monkeypatch, None)
    resp = await client.post("/api/playlists/song/analyze", json={"title": "x", "artist": "y"}, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "lyrics_not_found"


async def test_analyze_song_requires_auth(client):
    resp = await client.post("/api/playlists/song/analyze", json={"title": "t", "artist": "a"})
    assert resp.status_code == 401


async def test_add_word_known_marks_known_and_skips_exercises(app, client, monkeypatch):
    headers = await _login(app, client)
    calls = []
    monkeypatch.setattr("app.routers.playlists.schedule_refill", lambda bg, uid: calls.append(uid))

    resp = await client.post(
        "/api/playlists/song/word", json={"lemma": "dog", "language": "en", "known": True}, headers=headers
    )
    assert resp.status_code == 201
    assert resp.json() == {"added": True, "known": True}
    assert calls == []  # "I know it" must not generate exercises

    # it now counts as known -> analyze renders it green
    _patch_lyrics(monkeypatch, "The dog runs across the green field every single morning")
    a = await client.post("/api/playlists/song/analyze", json={"title": "t", "artist": "a"}, headers=headers)
    statuses = {t["surface"]: t["status"] for line in a.json()["lines"] for t in line["tokens"]}
    assert statuses["dog"] == "known"


async def test_add_word_learning_schedules_exercise_refill(app, client, monkeypatch):
    headers = await _login(app, client)
    calls = []
    monkeypatch.setattr("app.routers.playlists.schedule_refill", lambda bg, uid: calls.append(uid))

    resp = await client.post(
        "/api/playlists/song/word", json={"lemma": "cat", "language": "en", "known": False}, headers=headers
    )
    assert resp.status_code == 201
    assert resp.json() == {"added": True, "known": False}
    assert len(calls) == 1  # "add to learning" tops up the exercise pool

    # a learning word renders in the third (amber) state, not green/red
    _patch_lyrics(monkeypatch, "The cat runs across the green field every single morning")
    a = await client.post("/api/playlists/song/analyze", json={"title": "t", "artist": "a"}, headers=headers)
    statuses = {t["surface"]: t["status"] for line in a.json()["lines"] for t in line["tokens"]}
    assert statuses["cat"] == "learning"


async def test_add_word_is_idempotent(app, client, monkeypatch):
    headers = await _login(app, client)
    monkeypatch.setattr("app.routers.playlists.schedule_refill", lambda bg, uid: None)
    body = {"lemma": "cat", "language": "en", "known": True}
    await client.post("/api/playlists/song/word", json=body, headers=headers)
    again = await client.post("/api/playlists/song/word", json=body, headers=headers)
    assert again.json()["added"] is False  # already in the dictionary


async def test_translate_song_word_uses_context(app, client):
    headers = await _login(app, client)

    class _StubGen:
        async def generate_translation(self, params):
            assert params.sentence == "The cat and the dog"  # line passed as context
            # the surface form is translated, never our (possibly mangled) lemma
            assert params.word == "dogs"
            return GeneratedTranslation(translation="собаки", model="stub")

    app.dependency_overrides[get_exercise_generation_service] = lambda: _StubGen()
    resp = await client.post(
        "/api/playlists/song/translate",
        json={"word": "dogs", "lemma": "dog", "line": "The cat and the dog", "language": "en"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"word": "dogs", "translation": "собаки"}
