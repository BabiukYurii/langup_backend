"""Spoken audio: cache lookup, synthesis on a miss, and storage.

The gateway is stateless and re-synthesizes whatever it is asked for, so caching
is this side's job. The flow on every request is:

    hash(text, language, voice) -> row in audio_clips?
        hit  -> return its URL, nothing else happens
        miss -> gateway /tts -> WAV -> MP3 -> object storage -> row

Because the key covers only what was said and how, the cache is shared across
all users. That is what makes audio viable in lyrics, where one chorus repeats
the same handful of words many times over.
"""

import logging

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.exc import BadRequestException, ServiceUnavailableException
from app.database.postgres import get_session
from app.models import AudioClip
from app.repositories.audio_clip import AudioClipRepository
from app.services.ai.client import AIClient, get_ai_client
from app.services.audio.encode import AudioEncodingError, wav_duration_ms, wav_to_mp3
from app.services.audio.keys import clip_hash, normalize_text, object_key
from app.services.audio.storage import AudioStorage, AudioStorageError, get_audio_storage

logger = logging.getLogger(__name__)

AUDIO_DISABLED = "audio_disabled"
TEXT_TOO_LONG = "audio_text_too_long"


class AudioService:
    def __init__(self, repo: AudioClipRepository, storage: AudioStorage, ai: AIClient) -> None:
        self.repo = repo
        self.storage = storage
        self.ai = ai

    @staticmethod
    def resolve_voice(language: str, voice: str | None = None) -> str:
        """The voice `language` is spoken with, or an explicit override."""
        if voice:
            return voice
        cfg = settings.audio
        return cfg.voice_map.get(language.lower()[:2], cfg.AUDIO_FALLBACK_VOICE)

    async def get_or_create(self, text: str, language: str, voice: str | None = None) -> tuple[AudioClip, bool]:
        """(clip, was_cached) for `text`, synthesizing only on a miss.

        The flag is reported rather than re-derived by the caller: a second
        lookup to answer "was this a hit?" would cost a query on every request
        to save nothing.
        """
        cfg = settings.audio
        if not cfg.AUDIO_ENABLED:
            raise ServiceUnavailableException(AUDIO_DISABLED)

        text = normalize_text(text)
        if not text:
            raise BadRequestException("Nothing to speak")
        if len(text) > cfg.AUDIO_MAX_TEXT_LENGTH:
            raise BadRequestException(TEXT_TOO_LONG)

        # Resolve the voice BEFORE hashing. Letting the gateway choose would
        # make the key unknowable until after synthesis, so every request that
        # did not name a voice would miss the cache — which is most of them.
        used_voice = self.resolve_voice(language, voice)

        hash_ = clip_hash(text, language, used_voice)
        existing = await self.repo.get_by_hash(hash_)
        if existing:
            return existing, True

        wav, _reported = await self._synthesize(text, language, used_voice)

        try:
            mp3 = await wav_to_mp3(wav)
        except AudioEncodingError as e:
            logger.error("Encoding failed for %r: %s", text[:40], e)
            raise ServiceUnavailableException("Could not encode audio") from e

        key = object_key(hash_)
        try:
            await self.storage.put(key, mp3)
        except AudioStorageError as e:
            logger.error("Storing %s failed: %s", key, e)
            raise ServiceUnavailableException("Could not store audio") from e

        clip = await self.repo.create_one(
            {
                "hash": hash_,
                "text": text,
                "language": language,
                "voice": used_voice,
                "object_key": key,
                "duration_ms": wav_duration_ms(wav),
                "size_bytes": len(mp3),
            }
        )
        return clip, False

    async def read(self, hash_: str) -> tuple[bytes, AudioClip] | None:
        """(mp3 bytes, row) for a stored clip, or None if we cannot serve it."""
        clip = await self.repo.get_by_hash(hash_)
        if not clip:
            return None
        try:
            data = await self.storage.get(clip.object_key)
        except AudioStorageError as e:
            logger.error("Reading %s failed: %s", clip.object_key, e)
            return None
        if data is None:
            # Storage was wiped independently of the database. Drop the row so
            # the next request re-synthesizes instead of 404-ing forever.
            logger.warning("Clip %s missing from storage — dropping stale row", hash_)
            await self.repo.delete_one(clip)
            return None
        return data, clip

    async def _synthesize(self, text: str, language: str, voice: str | None) -> tuple[bytes, str]:
        try:
            return await self.ai.speak(text=text, language=language, voice=voice)
        except Exception as e:  # noqa: BLE001 — the gateway being down is a 503, not a 500
            logger.error("TTS failed for %r (%s): %s", text[:40], language, e)
            raise ServiceUnavailableException("Speech synthesis is unavailable") from e


async def get_audio_service(
    session: AsyncSession = Depends(get_session),
    storage: AudioStorage = Depends(get_audio_storage),
    ai: AIClient = Depends(get_ai_client),
) -> AudioService:
    return AudioService(AudioClipRepository(session), storage, ai)
