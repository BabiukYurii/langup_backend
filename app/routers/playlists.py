from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dependencies import CurrentUserDep
from app.schemas.playlist import (
    AnalyzedLyrics,
    PlaylistPreviewOut,
    PlaylistPreviewRequest,
    SongAnalyzeRequest,
    SongTranslateOut,
    SongTranslateRequest,
)
from app.services.songs.service import SongService, get_song_service
from app.services.spotify.playlist_parser import fetch_playlist_preview

router = APIRouter(prefix="/playlists", tags=["Playlists"])

SongServiceDep = Annotated[SongService, Depends(get_song_service)]


@router.post("/preview", response_model=PlaylistPreviewOut, status_code=status.HTTP_200_OK)
async def preview_playlist(data: PlaylistPreviewRequest, current_user: CurrentUserDep) -> PlaylistPreviewOut:
    """Read a public Spotify playlist's track list (title + artist only).

    Capped at PLAYLIST_MAX_TRACKS; the response's `truncated` flag lets the UI
    warn when a longer playlist had tracks skipped. No audio or lyrics.
    """
    return await fetch_playlist_preview(data.url)


@router.post("/song/analyze", response_model=AnalyzedLyrics, status_code=status.HTTP_200_OK)
async def analyze_song(
    data: SongAnalyzeRequest, current_user: CurrentUserDep, service: SongServiceDep
) -> AnalyzedLyrics:
    """Fetch a song's lyrics and mark each word known/unknown for this user.

    Translations are not included here (fast open); the client asks for them per
    word via /song/translate when the learner taps a red (unknown) word.
    """
    return await service.analyze_track(current_user.id, data.title, data.artist)


@router.post("/song/translate", response_model=SongTranslateOut, status_code=status.HTTP_200_OK)
async def translate_song_word(
    data: SongTranslateRequest, current_user: CurrentUserDep, service: SongServiceDep
) -> SongTranslateOut:
    """Translate one unknown word in the context of its song line (on tap)."""
    translation = await service.translate_in_context(current_user.id, data.lemma, data.line, data.language)
    return SongTranslateOut(lemma=data.lemma, translation=translation)
