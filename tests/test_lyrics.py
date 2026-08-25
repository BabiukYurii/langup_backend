import pytest

from app.services.lyrics import fetch_lyrics
from app.services.lyrics import lrclib as lrclib_mod
from app.services.lyrics.lrclib import LrclibProvider

pytestmark = pytest.mark.asyncio


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def _patch(monkeypatch, routes):
    """routes: {path: _Resp}. Missing path -> 404."""

    class _Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, path, params=None):
            return routes.get(path, _Resp(404, None))

    monkeypatch.setattr(lrclib_mod.httpx, "AsyncClient", lambda *a, **k: _Client())


async def test_lrclib_exact_match(monkeypatch):
    _patch(monkeypatch, {"/api/get": _Resp(200, {"plainLyrics": "line one\nline two"})})
    assert await LrclibProvider().fetch("Undead", "Hollywood Undead") == "line one\nline two"


async def test_lrclib_falls_back_to_search(monkeypatch):
    _patch(
        monkeypatch,
        {
            "/api/get": _Resp(404, None),
            "/api/search": _Resp(200, [{"plainLyrics": ""}, {"plainLyrics": "found via search"}]),
        },
    )
    assert await LrclibProvider().fetch("Song", "A, B") == "found via search"


async def test_lrclib_returns_none_when_missing(monkeypatch):
    _patch(monkeypatch, {"/api/get": _Resp(404, None), "/api/search": _Resp(200, [])})
    assert await LrclibProvider().fetch("Nope", "Nobody") is None


async def test_fetch_lyrics_uses_provider_chain(monkeypatch):
    _patch(monkeypatch, {"/api/get": _Resp(200, {"plainLyrics": "hi"})})
    assert await fetch_lyrics("t", "a") == "hi"
