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
from app.services.spotify.playlist_parser import extract_playlist_id, fetch_playlist_preview

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, int], None]


async def run_playlist_import(
    session: AsyncSession, user_id: int, url: str, on_progress: ProgressFn | None = None
) -> dict:
    """Create the playlist, link + analyse each track, report progress. Returns
    {playlist_uuid, songs}. Sets the playlist status to failed on any error."""
    spotify_id = extract_playlist_id(url)
    preview = await fetch_playlist_preview(url)

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
