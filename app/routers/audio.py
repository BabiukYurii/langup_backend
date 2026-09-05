import re
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core import settings
from app.core.config.audio import AUDIO_FORMATS
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

_BYTE_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def byte_span(header: str | None, size: int) -> tuple[int, int] | None:
    """The inclusive [start, end] a Range header asks for, or None for all of it.

    None means "answer with the whole body", which is always a valid reply to a
    Range request. So everything we choose not to implement — several ranges at
    once, a unit other than bytes, a span starting past the end — quietly falls
    back to a plain 200 rather than erroring. A clip is a few kilobytes; there
    is nothing to be won by being stricter than that.
    """
    if not header:
        return None
    match = _BYTE_RANGE.match(header.strip())
    if not match:
        return None
    first, last = match.groups()
    if not first and not last:
        return None
    if not first:  # `bytes=-N` asks for the trailing N bytes
        length = int(last)
        return (max(0, size - length), size - 1) if length else None
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    return (start, end) if start <= end < size else None


def mime_for(object_key: str) -> str:
    """The content type of a stored clip, judged by its own extension."""
    for fmt in AUDIO_FORMATS.values():
        if object_key.endswith(fmt.extension):
            return fmt.mime
    return settings.audio.format.mime


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
        url=f"/api/audio/{clip.hash}{settings.audio.format.extension}",
        hash=clip.hash,
        voice=clip.voice,
        duration_ms=clip.duration_ms,
        cached=cached,
    )


@router.get("/{filename}")
async def get_audio(filename: str, request: Request, service: AudioServiceDep) -> Response:
    """Stream a stored clip, honouring byte ranges.

    The extension is taken off rather than matched, so the route does not have
    to be rewritten when AUDIO_FORMAT changes — and a link handed out under the
    previous extension keeps resolving to the row, which then answers with
    whatever that clip actually is.

    Deliberately NOT behind authentication. An <audio> element cannot send an
    Authorization header, so gating this would force every clip through a blob
    fetch and throw away the browser cache — for a file that is a single spoken
    word, carries no personal data, and is addressed by a hash nobody can guess
    without already knowing the text.

    Ranges matter for exactly one platform. iOS plays through AVPlayer, which
    opens every clip with a `Range: bytes=0-1` probe and expects `206` back;
    answered with a plain `200` it stalls or drops the clip, which is why audio
    worked everywhere except on an iPhone. Android's ExoPlayer and the browser's
    <audio> element accept either answer, so serving ranges changes nothing for
    them.
    """
    hash_ = filename.rsplit(".", 1)[0]
    found = await service.read(hash_)
    if not found:
        raise ObjectNotFoundException(filename, "Audio clip")
    data, clip = found
    headers = {**_IMMUTABLE, "Accept-Ranges": "bytes", "X-Voice": clip.voice}
    # From the stored key, not the current setting: a clip written before a
    # format switch is still the old format and must be labelled as such.
    media_type = mime_for(clip.object_key)

    span = byte_span(request.headers.get("range"), len(data))
    if span is None:
        return Response(
            content=data,
            media_type=media_type,
            headers={**headers, "Content-Length": str(len(data))},
        )

    start, end = span
    body = data[start : end + 1]
    return Response(
        content=body,
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers={
            **headers,
            "Content-Range": f"bytes {start}-{end}/{len(data)}",
            "Content-Length": str(len(body)),
        },
    )
