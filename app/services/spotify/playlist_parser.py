"""Read a public Spotify playlist's track list from the embed page.

No API key or user login: the official /playlists/{id}/tracks endpoint is
blocked for new apps (Spotify's Nov-2024 change), but the embed page
(open.spotify.com/embed/playlist/{id}) ships the track list in a
`__NEXT_DATA__` JSON blob that a plain HTTP GET can read. Only titles and
artists are taken — never audio or lyrics.
"""

import json
import logging
import re

import httpx

from app.core import settings
from app.core.exc import BadRequestException
from app.schemas.playlist import PlaylistPreviewOut, PlaylistTrackOut

logger = logging.getLogger(__name__)

# open.spotify.com/playlist/{id}, /embed/playlist/{id}, or spotify:playlist:{id}.
_ID_RE = re.compile(r"(?:playlist[:/])([0-9A-Za-z]{22})")
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def extract_playlist_id(url: str) -> str:
    """The 22-char playlist id from a link/URI, else a 400."""
    match = _ID_RE.search(url or "")
    if not match:
        raise BadRequestException("Not a valid Spotify playlist link")
    return match.group(1)


def _tracks_from_next_data(html: str) -> tuple[str | None, list[PlaylistTrackOut]]:
    """Pull (playlist name, tracks) out of the embed page's __NEXT_DATA__ blob."""
    blob = _NEXT_DATA_RE.search(html)
    if not blob:
        raise BadRequestException("Could not read the playlist (unexpected page format)")
    try:
        entity = json.loads(blob.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Playlist embed parse failed: %s", e)
        raise BadRequestException("Could not read the playlist (unexpected page format)") from e

    tracks: list[PlaylistTrackOut] = []
    for item in entity.get("trackList") or []:
        title = (item.get("title") or "").strip()
        artist = (item.get("subtitle") or "").strip()
        if not title:
            continue
        # uri looks like "spotify:track:{id}"; keep the id when present.
        uri = item.get("uri") or ""
        track_id = uri.split(":")[-1] if uri.startswith("spotify:track:") else None
        tracks.append(PlaylistTrackOut(title=title, artist=artist, spotify_id=track_id))
    return entity.get("name"), tracks


async def fetch_playlist_preview(url: str) -> PlaylistPreviewOut:
    """Fetch a playlist and return its tracks, capped at PLAYLIST_MAX_TRACKS.

    `truncated` is set when the playlist has more tracks than the cap so the
    client can warn that the rest were skipped.
    """
    playlist_id = extract_playlist_id(url)
    embed_url = settings.playlists.PLAYLIST_EMBED_URL.format(id=playlist_id)
    try:
        async with httpx.AsyncClient(timeout=settings.playlists.PLAYLIST_FETCH_TIMEOUT_SECONDS) as client:
            resp = await client.get(embed_url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
    except httpx.HTTPError as e:
        logger.warning("Playlist fetch failed for %s: %s", playlist_id, e)
        raise BadRequestException("Could not reach Spotify. Try again.") from e
    if resp.status_code != 200:
        raise BadRequestException("Playlist not found or not public")

    name, tracks = _tracks_from_next_data(resp.text)
    limit = settings.playlists.PLAYLIST_MAX_TRACKS
    total = len(tracks)
    return PlaylistPreviewOut(
        name=name,
        tracks=tracks[:limit],
        total=total,
        truncated=total > limit,
        limit=limit,
    )
