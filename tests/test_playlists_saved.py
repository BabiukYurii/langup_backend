import pytest

from app.models import Playlist, PlaylistSong, Song, UserWord, Word
from app.services.auth.oauth_google import get_google_verifier

pytestmark = pytest.mark.asyncio

PROFILE = {"sub": "psv-sub-1", "email": "psv@gmail.com", "email_verified": True, "name": "Psv"}


async def _login(app, client):
    app.dependency_overrides[get_google_verifier] = lambda: lambda _t: PROFILE
    token = (await client.post("/api/auth/google", json={"id_token": "fake"})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _seed_playlist(session, user_id):
    song = Song(
        title="Undead",
        artist="Hollywood Undead",
        match_key="undead|hollywood undead",
        language="en",
        lemmas=["cat", "dog", "fox"],
        lyrics_found=True,
    )
    word = Word(lemma="cat", language="en")
    session.add_all([song, word])
    await session.flush()
    playlist = Playlist(user_id=user_id, spotify_id="abc", name="Rock", status="ready")
    session.add(playlist)
    await session.flush()
    session.add(PlaylistSong(playlist_uuid=playlist.uuid, song_uuid=song.uuid, position=0))
    session.add(UserWord(user_id=user_id, word_uuid=word.uuid))  # user knows "cat"
    await session.commit()
    return playlist


async def test_import_endpoint_returns_task_id(app, client, monkeypatch):
    headers = await _login(app, client)
    monkeypatch.setattr("app.routers.playlists.schedule_playlist_import", lambda bg, uid, url: "task-123")
    resp = await client.post(
        "/api/playlists", json={"url": "https://open.spotify.com/playlist/5g4ppcqdDHUCVpkAWQ5zbG"}, headers=headers
    )
    assert resp.status_code == 202
    assert resp.json() == {"task_id": "task-123"}


async def test_list_and_detail_with_unknown_counts(app, client, session):
    headers = await _login(app, client)
    me = (await client.get("/api/auth/me", headers=headers)).json()
    playlist = await _seed_playlist(session, me["id"])

    listing = await client.get("/api/playlists", headers=headers)
    assert listing.status_code == 200
    row = listing.json()[0]
    assert row["name"] == "Rock" and row["status"] == "ready" and row["song_count"] == 1

    detail = await client.get(f"/api/playlists/{playlist.uuid}", headers=headers)
    assert detail.status_code == 200
    song = detail.json()["songs"][0]
    assert song["title"] == "Undead"
    assert song["language"] == "en"
    assert song["unknown_count"] == 2  # 3 lemmas minus the known "cat"
    assert song["in_learned_language"] is True


async def test_detail_hides_songs_in_non_learned_languages(app, client, session):
    headers = await _login(app, client)
    me = (await client.get("/api/auth/me", headers=headers)).json()
    playlist = await _seed_playlist(session, me["id"])  # user learns en (has an en word)

    # add a Ukrainian song to the same playlist — user doesn't learn uk
    uk_song = Song(
        title="Букети", artist="MOLLY", match_key="букети|molly", language="uk", lemmas=["букет"], lyrics_found=True
    )
    session.add(uk_song)
    await session.flush()
    session.add(PlaylistSong(playlist_uuid=playlist.uuid, song_uuid=uk_song.uuid, position=1))
    await session.commit()

    detail = await client.get(f"/api/playlists/{playlist.uuid}", headers=headers)
    titles = [s["title"] for s in detail.json()["songs"]]
    assert titles == ["Undead"]  # the uk song is hidden; only the en one remains


async def test_delete_playlist(app, client, session):
    headers = await _login(app, client)
    me = (await client.get("/api/auth/me", headers=headers)).json()
    playlist = await _seed_playlist(session, me["id"])

    assert (await client.delete(f"/api/playlists/{playlist.uuid}", headers=headers)).status_code == 204
    assert (await client.get(f"/api/playlists/{playlist.uuid}", headers=headers)).status_code == 404


async def test_saved_playlist_endpoints_require_auth(client):
    assert (await client.get("/api/playlists")).status_code == 401
    assert (await client.post("/api/playlists", json={"url": "x"})).status_code == 401
