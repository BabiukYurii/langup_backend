from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core import settings
from app.core.exc import ObjectNotFoundException
from app.dependencies import CurrentUserDep
from app.schemas.audio import AudioOut, AudioRequest, VoicesOut
from app.services.audio.keys import LEGACY_VOICE_PREF_KEY, VOICES_PREF_KEY
from app.services.audio.service import AudioService, get_audio_service

router = APIRouter(prefix="/audio", tags=["Audio"])

AudioServiceDep = Annotated[AudioService, Depends(get_audio_service)]

# A clip is immutable: its URL contains a hash of exactly what was spoken, so
# the same URL can never return different audio. Telling the browser to keep it
# for a year means a word is fetched once per device, ever.
_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


def saved_voices(current_user) -> dict[str, str]:
    """The learner's language -> voice choices, ignoring anything unusable.

    Filtered against the engine's roster so a stale or hand-edited preference
    cannot send a voice the model does not have.
    """
    prefs = current_user.preferences or {}
    stored = prefs.get(VOICES_PREF_KEY)
    available = settings.audio.available_voices

    if isinstance(stored, dict):
        return {str(lang).lower()[:2]: voice for lang, voice in stored.items() if voice in available}
    # Continuity with the first cut, which stored one voice for the whole
    # account: apply it to every language until per-language choices replace it.
    legacy = prefs.get(LEGACY_VOICE_PREF_KEY)
    if legacy in available:
        return dict.fromkeys(settings.audio.voice_map, legacy)
    return {}


def chosen_voice(current_user, language: str, requested: str | None) -> str | None:
    """The voice to speak `language` with: the request's, else the learner's.

    Applied here rather than in the service so the service stays user-agnostic
    — it caches by voice, not by who asked. An explicit voice still wins, which
    is what lets the profile picker preview one before it is saved.
    """
    if requested:
        return requested
    return saved_voices(current_user).get((language or "").lower()[:2])


@router.get("/voices", response_model=VoicesOut)
async def list_voices(current_user: CurrentUserDep) -> VoicesOut:
    """What the profile picker offers, and what is chosen per language."""
    return VoicesOut(
        voices=settings.audio.available_voices,
        selected=saved_voices(current_user),
        defaults=settings.audio.voice_map,
    )


@router.post("", response_model=AudioOut, status_code=status.HTTP_200_OK)
async def create_audio(data: AudioRequest, current_user: CurrentUserDep, service: AudioServiceDep) -> AudioOut:
    """The URL to play `text` from, synthesizing it only if it is not cached.

    Authenticated: synthesis costs CPU, so only logged-in users may trigger it.
    Playback itself (the GET below) is open — see the note there.
    """
    voice = chosen_voice(current_user, data.language, data.voice)
    clip, cached = await service.get_or_create(data.text, data.language, voice)
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
