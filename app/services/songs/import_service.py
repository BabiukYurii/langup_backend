"""Import a Spotify playlist and analyse every song, with progress.

Runs on a Celery worker (survives restarts, keeps the AI/network work off the
request path); falls back to FastAPI BackgroundTasks when no worker is up. Songs
are shared and cached, so re-imports and other users' imports are cheap.
"""

import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.repositories.playlist import PlaylistRepository, PlaylistSongRepository
from app.services.songs.store import analyze_song, get_or_create_song
from app.services.spotify.playlist_parser import extract_playlist_id, fetch_playlist_full, fetch_track

# Pasted singles are collected under one playlist per user rather than a row
# each, so the list does not fill up with one-song entries. The marker sits in
# spotify_id because that is what identifies a playlist's origin, and no real
# Spotify id is 7 characters long.
SINGLES_MARKER = "singles"
SINGLES_NAME = "Single tracks"

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, int], None]


async def run_playlist_import(
    session: AsyncSession, user_id: int, url: str, on_progress: ProgressFn | None = None
) -> dict:
    """Create the playlist, link + analyse each track, report progress. Returns
    {playlist_uuid, songs}. Sets the playlist status to failed on any error."""
    spotify_id = extract_playlist_id(url)
    preview = await fetch_playlist_full(url)

    playlists = PlaylistRepository(session)
    links = PlaylistSongRepository(session)
    playlist = await playlists.create_one(
        {"user_id": user_id, "spotify_id": spotify_id, "name": preview.name, "status": "parsing"}
    )

    total = len(preview.tracks)
    try:
        for i, track in enumerate(preview.tracks):
            song = await get_or_create_song(session, track.title, track.artist, track.spotify_id)
            if not await links.get_one(playlist_uuid=playlist.uuid, song_uuid=song.uuid):
                await links.create_one({"playlist_uuid": playlist.uuid, "song_uuid": song.uuid, "position": i})
            await analyze_song(session, song)  # cached, so cheap on repeats
            if on_progress:
                on_progress(i + 1, total)
    except Exception:
        await playlists.update_one(playlist, {"status": "failed"})
        raise

    await playlists.update_one(playlist, {"status": "ready"})
    return {"playlist_uuid": str(playlist.uuid), "songs": total}


async def run_track_import(session: AsyncSession, user_id: int, url: str) -> dict:
    """Save one pasted track and put it at the front of the warming queue.

    Done inline rather than queued: it is one page from Spotify, one lyrics
    fetch and an offline analysis, and somebody who pasted a single song wants
    to open it now — so the response carries the ids to navigate to instead of
    a task to poll.
    """
    track = await fetch_track(url)
    playlists = PlaylistRepository(session)
    links = PlaylistSongRepository(session)

    playlist = await playlists.get_one(user_id=user_id, spotify_id=SINGLES_MARKER)
    if not playlist:
        playlist = await playlists.create_one(
            {"user_id": user_id, "spotify_id": SINGLES_MARKER, "name": SINGLES_NAME, "status": "ready"}
        )

    song = await get_or_create_song(session, track.title, track.artist, track.spotify_id)
    # One more than the highest so far: every single outranks every playlist
    # track (which stay at 0) and the newest single leads the others. An
    # ordinal, not a timestamp — two tracks pasted in the same second still
    # have an order, and seconds cannot express it.
    priority = await links.max_priority(playlist.uuid) + 1
    link = await links.get_one(playlist_uuid=playlist.uuid, song_uuid=song.uuid)
    if link:
        await links.update_one(link, {"priority": priority})  # re-pasted: back to the front
    else:
        await links.create_one(
            {"playlist_uuid": playlist.uuid, "song_uuid": song.uuid, "position": 0, "priority": priority}
        )

    await analyze_song(session, song)  # shared and cached, so a known song is free
    await _reopen_warming(session, song.uuid)
    return {
        "playlist_uuid": str(playlist.uuid),
        "song_uuid": str(song.uuid),
        "title": track.title,
        "artist": track.artist,
        "songs": 1,
    }


async def _reopen_warming(session: AsyncSession, song_uuid) -> None:
    """Give a song the warmer had given up on another chance.

    A pair that ran out of fruitless attempts is out of the rotation for good;
    asking for that song by name is the clearest possible signal that it should
    be tried again. A pair already finished is left alone — it is warm, which is
    the whole point.
    """
    from app.repositories.song_warm_state import SongWarmStateRepository

    repo = SongWarmStateRepository(session)
    rows, _ = await repo.get_many(song_uuid=song_uuid, limit=50)
    for row in rows:
        if row.completed_at is None and (row.fruitless_attempts or 0):
            await repo.update_one(row, {"fruitless_attempts": 0})


async def import_track_in_background(user_id: int, url: str) -> None:
    """Fallback runner for a single track (no worker); never raises."""
    from app.database.postgres import async_session

    try:
        async with async_session() as session:
            await run_track_import(session, user_id, url)
    except Exception:  # noqa: BLE001 — a background job must never crash the process
        logger.exception("Background track import failed for user %s", user_id)


async def import_playlist_in_background(user_id: int, url: str) -> None:
    """Fallback runner (no worker): its own session, never raises to the caller."""
    from app.database.postgres import async_session

    try:
        async with async_session() as session:
            await run_playlist_import(session, user_id, url)
    except Exception:  # noqa: BLE001 — a background job must never crash the process
        logger.exception("Background playlist import failed for user %s", user_id)


def schedule_playlist_import(background, user_id: int, url: str) -> str | None:
    """Queue the import on Celery (returns a task id to poll), else run in-process."""
    if settings.celery.CELERY_ENABLED:
        try:
            from app.celery.tasks.playlist_tasks import import_playlist

            return import_playlist.delay(user_id, url).id
        except Exception:  # noqa: BLE001 — broker outage must not fail the request
            logger.exception("Could not enqueue playlist import; running in-process")
    background.add_task(import_playlist_in_background, user_id, url)
    return None


def playlist_import_status(task_id: str) -> dict:
    """Progress of a queued playlist import, for the client to poll."""
    from app.celery.config import celery_app

    result = celery_app.AsyncResult(task_id)
    state = result.state
    out = {"status": "pending", "done": None, "total": None, "playlist_uuid": None}

    if state == "PROGRESS" and isinstance(result.info, dict):
        out.update(status="running", done=result.info.get("done"), total=result.info.get("total"))
    elif state == "SUCCESS" and isinstance(result.result, dict):
        out.update(status="done", playlist_uuid=result.result.get("playlist_uuid"))
    elif state in ("STARTED", "RETRY"):
        out["status"] = "running"
    elif state in ("PENDING", "RECEIVED"):
        out["status"] = "pending"
    elif state == "SUCCESS":
        out["status"] = "done"
    else:
        out["status"] = "failed"
    return out
