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
# The same three shapes for a single track.
_TRACK_ID_RE = re.compile(r"(?:track[:/])([0-9A-Za-z]{22})")
_TRACK_EMBED_URL = "https://open.spotify.com/embed/track/{id}"
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def extract_playlist_id(url: str) -> str:
    """The 22-char playlist id from a link/URI, else a 400."""
    match = _ID_RE.search(url or "")
    if not match:
        raise BadRequestException("Not a valid Spotify playlist link")
    return match.group(1)


def extract_track_id(url: str) -> str:
    """The 22-char track id from a link/URI, else a 400."""
    match = _TRACK_ID_RE.search(url or "")
    if not match:
        raise BadRequestException("Not a valid Spotify track link")
    return match.group(1)


def link_kind(url: str) -> str:
    """Whether a pasted link points at a playlist or a single track.

    Checked before the id patterns rather than by trying each in turn, because
    the same field accepts both and the answer decides which import runs.
    """
    text = url or ""
    if _TRACK_ID_RE.search(text):
        return "track"
    if _ID_RE.search(text):
        return "playlist"
    raise BadRequestException("Not a valid Spotify playlist or track link")


def _entity_from_next_data(html: str) -> dict:
    """The embed page's entity blob, whatever kind of thing it describes."""
    blob = _NEXT_DATA_RE.search(html)
    if not blob:
        raise BadRequestException("Could not read the page (unexpected format)")
    try:
        return json.loads(blob.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Spotify embed parse failed: %s", e)
        raise BadRequestException("Could not read the page (unexpected format)") from e


async def _fetch_embed(url: str, what: str) -> str:
    """GET an embed page, turning every failure into a readable 400."""
    try:
        async with httpx.AsyncClient(timeout=settings.playlists.PLAYLIST_FETCH_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
    except httpx.HTTPError as e:
        logger.warning("Spotify fetch failed for %s: %s", url, e)
        raise BadRequestException("Could not reach Spotify. Try again.") from e
    if resp.status_code != 200:
        raise BadRequestException(f"{what} not found or not public")
    return resp.text


async def fetch_track(url: str) -> PlaylistTrackOut:
    """Title and artist of one track from its embed page.

    A track's entity is shaped differently from a playlist's: there is no
    trackList, and `subtitle` is empty — the performer lives in `artists`, as a
    list, joined here the way a playlist's subtitle already presents them.
    """
    track_id = extract_track_id(url)
    entity = _entity_from_next_data(await _fetch_embed(_TRACK_EMBED_URL.format(id=track_id), "Track"))

    title = (entity.get("title") or entity.get("name") or "").strip()
    if not title:
        raise BadRequestException("Could not read the track")
    artists = [(a.get("name") or "").strip() for a in entity.get("artists") or []]
    return PlaylistTrackOut(title=title, artist=", ".join(a for a in artists if a), spotify_id=track_id)


def _tracks_from_next_data(html: str) -> tuple[str | None, list[PlaylistTrackOut]]:
    """Pull (playlist name, tracks) out of the embed page's __NEXT_DATA__ blob."""
    entity = _entity_from_next_data(html)
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


async def fetch_playlist_full(url: str) -> PlaylistPreviewOut:
    """Best available track list for import.

    Uses the headless browser (whole playlist) when PLAYLIST_USE_BROWSER is on,
    falling back to the embed (~100 tracks) if the browser path errors; otherwise
    the embed. Result is capped at PLAYLIST_MAX_TRACKS with a `truncated` flag.
    """
    if not settings.playlists.PLAYLIST_USE_BROWSER:
        return await fetch_playlist_preview(url)

    playlist_id = extract_playlist_id(url)
    limit = settings.playlists.PLAYLIST_MAX_TRACKS
    try:
        from app.services.spotify.playlist_browser import fetch_playlist_via_browser

        name, tracks = await fetch_playlist_via_browser(
            playlist_id, limit, settings.playlists.PLAYLIST_BROWSER_TIMEOUT_SECONDS
        )
        if tracks:
            return PlaylistPreviewOut(
                name=name, tracks=tracks, total=len(tracks), truncated=len(tracks) >= limit, limit=limit
            )
        logger.warning("Browser parse returned no tracks for %s; falling back to embed", playlist_id)
    except Exception as e:  # noqa: BLE001 — any browser failure falls back to embed
        logger.warning("Browser parse failed for %s: %s; falling back to embed", playlist_id, e)
    return await fetch_playlist_preview(url)
