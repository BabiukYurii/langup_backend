from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres import get_session
from app.dependencies import CurrentUserDep
from app.schemas.playlist import (
    AnalyzedLyrics,
    PlaylistDetailOut,
    PlaylistImportOut,
    PlaylistImportRequest,
    PlaylistImportStatus,
    PlaylistOut,
    PlaylistPreviewOut,
    PlaylistPreviewRequest,
    SongAddWordOut,
    SongAddWordRequest,
    SongAnalyzeRequest,
    SongTranslateOut,
    SongTranslateRequest,
)
from app.services.learning.background import schedule_word_exercises
from app.services.songs.import_service import (
    playlist_import_status,
    run_track_import,
    schedule_playlist_import,
)
from app.services.songs.service import SongService, get_song_service
from app.services.spotify.playlist_parser import fetch_playlist_preview, fetch_track, link_kind

router = APIRouter(prefix="/playlists", tags=["Playlists"])

SongServiceDep = Annotated[SongService, Depends(get_song_service)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/preview", response_model=PlaylistPreviewOut, status_code=status.HTTP_200_OK)
async def preview_playlist(data: PlaylistPreviewRequest, current_user: CurrentUserDep) -> PlaylistPreviewOut:
    """Read what a pasted Spotify link contains (titles and artists only).

    Accepts a playlist or a single track, because the UI has one field for
    both. A playlist is capped at PLAYLIST_MAX_TRACKS and the `truncated` flag
    lets the client warn that the rest were skipped. No audio or lyrics.
    """
    if link_kind(data.url) == "track":
        track = await fetch_track(data.url)
        return PlaylistPreviewOut(name=track.title, tracks=[track], total=1, truncated=False, limit=1)
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
    translation = await service.translate_in_context(current_user.id, data.word, data.line, data.language)
    return SongTranslateOut(word=data.word, translation=translation)


@router.post("/song/word", response_model=SongAddWordOut, status_code=status.HTTP_201_CREATED)
async def add_song_word(
    data: SongAddWordRequest,
    current_user: CurrentUserDep,
    service: SongServiceDep,
    background: BackgroundTasks,
) -> SongAddWordOut:
    """Add a tapped word to the dictionary.

    `known=true` marks it as already known (no exercises); `known=false` adds it
    for learning and schedules the exercise pool to be topped up with it.
    """
    user_word_uuid = await service.add_word(current_user.id, data.lemma, data.language, data.known)
    # This word's own full set, not a pool top-up: a word tapped in a song is
    # exactly one the learner means to practise next.
    if user_word_uuid and not data.known:
        schedule_word_exercises(background, current_user.id, user_word_uuid)
    return SongAddWordOut(added=user_word_uuid is not None, known=data.known)


# --- saved playlists -------------------------------------------------------


@router.post("", response_model=PlaylistImportOut, status_code=status.HTTP_202_ACCEPTED)
async def import_playlist(
    data: PlaylistImportRequest,
    current_user: CurrentUserDep,
    background: BackgroundTasks,
    session: SessionDep,
) -> PlaylistImportOut:
    """Import whatever was pasted: a whole playlist, or one song.

    A playlist is parsed and analysed in the background, and the response is a
    task id to poll. A single track is done inline — one page from Spotify, one
    lyrics lookup — and comes back with the ids to open it, because somebody who
    pasted one song means to read that song now. It also jumps the warming
    queue ahead of every playlist.
    """
    if link_kind(data.url) == "track":
        result = await run_track_import(session, current_user.id, data.url)
        return PlaylistImportOut(
            kind="track", **{k: result[k] for k in ("playlist_uuid", "song_uuid", "title", "artist")}
        )
    task_id = schedule_playlist_import(background, current_user.id, data.url)
    return PlaylistImportOut(task_id=task_id)


@router.get("", response_model=list[PlaylistOut])
async def list_playlists(current_user: CurrentUserDep, service: SongServiceDep) -> list[PlaylistOut]:
    """The user's saved playlists, newest first."""
    return await service.list_playlists(current_user.id)


@router.get("/import/{task_id}", response_model=PlaylistImportStatus)
async def playlist_import_progress(task_id: str, current_user: CurrentUserDep) -> PlaylistImportStatus:
    """Progress of a queued playlist import, so the UI can show a bar."""
    return PlaylistImportStatus(**playlist_import_status(task_id))


@router.get("/{playlist_uuid}", response_model=PlaylistDetailOut)
async def get_playlist(playlist_uuid: UUID, current_user: CurrentUserDep, service: SongServiceDep) -> PlaylistDetailOut:
    """One saved playlist with its songs and the user's per-song new-word counts."""
    return await service.playlist_detail(current_user.id, playlist_uuid)


@router.delete("/{playlist_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playlist(playlist_uuid: UUID, current_user: CurrentUserDep, service: SongServiceDep) -> None:
    """Remove a saved playlist (its song links go via cascade)."""
    await service.delete_playlist(current_user.id, playlist_uuid)
