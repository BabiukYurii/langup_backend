from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.exc import ObjectNotFoundException
from app.dependencies import CurrentUserDep
from app.schemas.audio import AudioOut, AudioRequest
from app.services.audio.service import AudioService, get_audio_service

router = APIRouter(prefix="/audio", tags=["Audio"])

AudioServiceDep = Annotated[AudioService, Depends(get_audio_service)]

# A clip is immutable: its URL contains a hash of exactly what was spoken, so
# the same URL can never return different audio. Telling the browser to keep it
# for a year means a word is fetched once per device, ever.
_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


@router.post("", response_model=AudioOut, status_code=status.HTTP_200_OK)
async def create_audio(data: AudioRequest, current_user: CurrentUserDep, service: AudioServiceDep) -> AudioOut:
    """The URL to play `text` from, synthesizing it only if it is not cached.

    Authenticated: synthesis costs CPU, so only logged-in users may trigger it.
    Playback itself (the GET below) is open — see the note there.
    """
    clip, cached = await service.get_or_create(data.text, data.language, data.voice)
    return AudioOut(
        url=f"/api/audio/{clip.hash}.mp3",
        hash=clip.hash,
        voice=clip.voice,
        duration_ms=clip.duration_ms,
        cached=cached,
    )


@router.get("/{hash_}.mp3")
async def get_audio(hash_: str, service: AudioServiceDep) -> Response:
    """Stream a stored clip.

    Deliberately NOT behind authentication. An <audio> element cannot send an
    Authorization header, so gating this would force every clip through a blob
    fetch and throw away the browser cache — for a file that is a single spoken
    word, carries no personal data, and is addressed by a hash nobody can guess
    without already knowing the text.
    """
    found = await service.read(hash_)
    if not found:
        raise ObjectNotFoundException(hash_, "Audio clip")
    data, clip = found
    return Response(
        content=data,
        media_type="audio/mpeg",
        headers={
            **_IMMUTABLE,
            "Content-Length": str(len(data)),
            "X-Voice": clip.voice,
        },
    )
