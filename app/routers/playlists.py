from fastapi import APIRouter, status

from app.dependencies import CurrentUserDep
from app.schemas.playlist import PlaylistPreviewOut, PlaylistPreviewRequest
from app.services.spotify.playlist_parser import fetch_playlist_preview

router = APIRouter(prefix="/playlists", tags=["Playlists"])


@router.post("/preview", response_model=PlaylistPreviewOut, status_code=status.HTTP_200_OK)
async def preview_playlist(data: PlaylistPreviewRequest, current_user: CurrentUserDep) -> PlaylistPreviewOut:
    """Read a public Spotify playlist's track list (title + artist only).

    Capped at PLAYLIST_MAX_TRACKS; the response's `truncated` flag lets the UI
    warn when a longer playlist had tracks skipped. No audio or lyrics.
    """
    return await fetch_playlist_preview(data.url)
