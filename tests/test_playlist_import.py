from uuid import UUID

import pytest

from app.models import Playlist, PlaylistSong, User
from app.schemas.playlist import PlaylistPreviewOut, PlaylistTrackOut
from app.services.songs import import_service, store
from app.services.songs.import_service import run_playlist_import

pytestmark = pytest.mark.asyncio

URL = "https://open.spotify.com/playlist/5g4ppcqdDHUCVpkAWQ5zbG"


def _preview(n):
    tracks = [PlaylistTrackOut(title=f"Song {i}", artist=f"Artist {i}", spotify_id=f"t{i}") for i in range(n)]
    return PlaylistPreviewOut(name="Rock", tracks=tracks, total=n, truncated=False, limit=50)


def _patch(monkeypatch, n, lyrics="The cat and the dog run in the park every single morning"):
    async def fake_preview(url):
        return _preview(n)

    async def fake_lyrics(title, artist):
        return lyrics

    monkeypatch.setattr(import_service, "fetch_playlist_full", fake_preview)
    monkeypatch.setattr(store, "fetch_lyrics", fake_lyrics)


async def _user(session, email="imp@x.com"):
    u = User(email=email)
    session.add(u)
    await session.flush()
    return u.id


async def test_import_creates_playlist_links_and_analyses(session, monkeypatch):
    user_id = await _user(session)
    _patch(monkeypatch, 3)
    progress = []

    result = await run_playlist_import(session, user_id, URL, on_progress=lambda d, t: progress.append((d, t)))

    assert result["songs"] == 3
    assert progress == [(1, 3), (2, 3), (3, 3)]

    playlist = await session.get(Playlist, UUID(result["playlist_uuid"]))
    assert playlist.status == "ready"
    assert playlist.name == "Rock"

    from sqlalchemy import select

    links = (
        (await session.execute(select(PlaylistSong).where(PlaylistSong.playlist_uuid == playlist.uuid))).scalars().all()
    )
    assert len(links) == 3

    from app.repositories.playlist import PlaylistSongRepository

    songs = await PlaylistSongRepository(session).songs_for_playlist(playlist.uuid)
    assert all(song.analyzed_at is not None and song.language == "en" for _, song in songs)
    assert any("cat" in (song.lemmas or []) for _, song in songs)


async def test_import_reuses_cached_song_across_playlists(session, monkeypatch):
    user_id = await _user(session, "imp2@x.com")
    _patch(monkeypatch, 2)
    r1 = await run_playlist_import(session, user_id, URL)
    r2 = await run_playlist_import(session, user_id, URL)  # same tracks -> same shared songs

    from sqlalchemy import func, select

    from app.models import Song

    song_count = (await session.execute(select(func.count()).select_from(Song))).scalar()
    assert song_count == 2  # deduped, not 4
    assert r1["playlist_uuid"] != r2["playlist_uuid"]  # two playlists though


async def test_import_marks_failed_on_error(session, monkeypatch):
    user_id = await _user(session, "imp3@x.com")

    async def boom_preview(url):
        return _preview(2)

    async def boom_lyrics(title, artist):
        raise RuntimeError("network down")

    monkeypatch.setattr(import_service, "fetch_playlist_full", boom_preview)
    monkeypatch.setattr(store, "fetch_lyrics", boom_lyrics)

    with pytest.raises(RuntimeError):
        await run_playlist_import(session, user_id, URL)

    from sqlalchemy import select

    playlist = (await session.execute(select(Playlist).where(Playlist.user_id == user_id))).scalar_one()
    assert playlist.status == "failed"
