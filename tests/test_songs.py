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
    session.add(UserWord(user_id=me["id"], word_uuid=word.uuid))
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


async def test_translate_song_word_uses_context(app, client):
    headers = await _login(app, client)

    class _StubGen:
        async def generate_translation(self, params):
            assert params.sentence == "The cat and the dog"  # line passed as context
            return GeneratedTranslation(translation="собака", model="stub")

    app.dependency_overrides[get_exercise_generation_service] = lambda: _StubGen()
    resp = await client.post(
        "/api/playlists/song/translate",
        json={"lemma": "dog", "line": "The cat and the dog", "language": "en"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"lemma": "dog", "translation": "собака"}
