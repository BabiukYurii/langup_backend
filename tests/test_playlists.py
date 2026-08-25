import json

import pytest

from app.core import settings
from app.core.exc import BadRequestException
from app.services.auth.oauth_google import get_google_verifier
from app.services.spotify import playlist_parser
from app.services.spotify.playlist_parser import extract_playlist_id, fetch_playlist_preview

pytestmark = pytest.mark.asyncio

PROFILE = {"sub": "pl-sub-1", "email": "pl@gmail.com", "email_verified": True, "name": "Pl"}


def _embed_html(name: str, n: int) -> str:
    """A minimal Spotify embed page carrying `n` tracks in __NEXT_DATA__."""
    track_list = [
        {"title": f"Song {i}", "subtitle": f"Artist {i}", "uri": f"spotify:track:id{i:022d}"} for i in range(n)
    ]
    data = {"props": {"pageProps": {"state": {"data": {"entity": {"name": name, "trackList": track_list}}}}}}
    return f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'


class _FakeResp:
    def __init__(self, status: int, text: str) -> None:
        self.status_code = status
        self.text = text


def _patch_fetch(monkeypatch, html: str, status: int = 200) -> None:
    class _FakeClient:
        def __init__(self, *a, **k) -> None: ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _FakeResp(status, html)

    monkeypatch.setattr(playlist_parser.httpx, "AsyncClient", lambda *a, **k: _FakeClient())


# --- id extraction ---------------------------------------------------------


async def test_extract_playlist_id_from_various_forms():
    pid = "5g4ppcqdDHUCVpkAWQ5zbG"
    assert extract_playlist_id(f"https://open.spotify.com/playlist/{pid}?si=abc") == pid
    assert extract_playlist_id(f"https://open.spotify.com/embed/playlist/{pid}") == pid
    assert extract_playlist_id(f"spotify:playlist:{pid}") == pid


async def test_extract_playlist_id_rejects_junk():
    with pytest.raises(BadRequestException):
        extract_playlist_id("https://example.com/not-a-playlist")


# --- parsing + cap ---------------------------------------------------------


async def test_preview_returns_tracks(monkeypatch):
    _patch_fetch(monkeypatch, _embed_html("My Mix", 3))
    out = await fetch_playlist_preview("https://open.spotify.com/playlist/5g4ppcqdDHUCVpkAWQ5zbG")
    assert out.name == "My Mix"
    assert out.total == 3
    assert out.truncated is False
    assert [t.title for t in out.tracks] == ["Song 0", "Song 1", "Song 2"]
    assert out.tracks[0].artist == "Artist 0"
    assert out.tracks[0].spotify_id == "id" + "0".zfill(22)


async def test_preview_caps_and_flags_truncation(monkeypatch):
    limit = settings.playlists.PLAYLIST_MAX_TRACKS
    _patch_fetch(monkeypatch, _embed_html("Big", limit + 20))
    out = await fetch_playlist_preview("https://open.spotify.com/playlist/5g4ppcqdDHUCVpkAWQ5zbG")
    assert out.total == limit + 20
    assert out.truncated is True
    assert out.limit == limit
    assert len(out.tracks) == limit  # only the first `limit` are processed


async def test_preview_bad_page_format(monkeypatch):
    _patch_fetch(monkeypatch, "<html>no next data here</html>")
    with pytest.raises(BadRequestException):
        await fetch_playlist_preview("https://open.spotify.com/playlist/5g4ppcqdDHUCVpkAWQ5zbG")


async def test_preview_non_200(monkeypatch):
    _patch_fetch(monkeypatch, "", status=404)
    with pytest.raises(BadRequestException):
        await fetch_playlist_preview("https://open.spotify.com/playlist/5g4ppcqdDHUCVpkAWQ5zbG")


# --- endpoint --------------------------------------------------------------


async def test_preview_endpoint_requires_auth(client):
    resp = await client.post("/api/playlists/preview", json={"url": "spotify:playlist:5g4ppcqdDHUCVpkAWQ5zbG"})
    assert resp.status_code == 401


async def test_preview_endpoint_returns_capped_tracks(app, client, monkeypatch):
    app.dependency_overrides[get_google_verifier] = lambda: lambda _t: PROFILE
    token = (await client.post("/api/auth/google", json={"id_token": "fake"})).json()["access_token"]
    _patch_fetch(monkeypatch, _embed_html("Rock", 3))

    resp = await client.post(
        "/api/playlists/preview",
        json={"url": "https://open.spotify.com/playlist/5g4ppcqdDHUCVpkAWQ5zbG"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Rock"
    assert body["total"] == 3
    assert body["truncated"] is False
    assert len(body["tracks"]) == 3
