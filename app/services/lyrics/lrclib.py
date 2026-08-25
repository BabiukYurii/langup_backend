"""LRCLIB lyrics provider (https://lrclib.net) — free, no API key.

Tries the exact-match endpoint first, then a search, and only ever reads
`plainLyrics` (we don't need synced/timed lyrics). Returns None on any miss so
a song without findable lyrics is simply skipped, never an error.
"""

import logging

import httpx

from app.core import settings

logger = logging.getLogger(__name__)


class LrclibProvider:
    name = "lrclib"

    def __init__(self) -> None:
        self._base = settings.playlists.LRCLIB_BASE_URL
        self._timeout = settings.playlists.LYRICS_FETCH_TIMEOUT_SECONDS

    async def fetch(self, title: str, artist: str) -> str | None:
        # LRCLIB matches a single artist; a multi-artist string ("A, B") is
        # trimmed to the first name for the exact lookup, with search as backup.
        primary_artist = artist.split(",")[0].strip()
        async with httpx.AsyncClient(timeout=self._timeout, base_url=self._base) as client:
            lyrics = await self._get(client, title, primary_artist)
            if lyrics:
                return lyrics
            return await self._search(client, title, artist)

    async def _get(self, client: httpx.AsyncClient, title: str, artist: str) -> str | None:
        try:
            resp = await client.get("/api/get", params={"track_name": title, "artist_name": artist})
        except httpx.HTTPError as e:
            logger.warning("LRCLIB get failed for %r: %s", title, e)
            return None
        if resp.status_code != 200:
            return None
        return (resp.json() or {}).get("plainLyrics") or None

    async def _search(self, client: httpx.AsyncClient, title: str, artist: str) -> str | None:
        try:
            resp = await client.get("/api/search", params={"track_name": title, "artist_name": artist})
        except httpx.HTTPError as e:
            logger.warning("LRCLIB search failed for %r: %s", title, e)
            return None
        if resp.status_code != 200:
            return None
        for hit in resp.json() or []:
            if hit.get("plainLyrics"):
                return hit["plainLyrics"]
        return None
