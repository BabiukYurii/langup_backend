# Spoken audio: where clips are stored and how they are encoded.
from app.core.config.base import BaseConfig


class AudioConfig(BaseConfig):
    AUDIO_ENABLED: bool = True

    # language -> voice. Voice resolution belongs HERE, not in the gateway:
    # the cache key includes the voice, so a request that does not name one
    # could not be looked up before synthesis — every such call would miss the
    # cache and hit the gateway. Deciding locally makes the key computable up
    # front. It is also where per-user voices land in the profile picker.
    AUDIO_VOICES: str = "en=M1,uk=F1,pl=F1,de=M1,es=F1,fr=F1,it=M1,pt=F1"
    AUDIO_FALLBACK_VOICE: str = "F1"
    # Voices the learner may choose from in their profile. Supertonic-3 ships
    # ten; listing them here (rather than in the page) keeps the picker honest
    # if the engine's roster ever changes.
    AUDIO_AVAILABLE_VOICES: str = "M1,M2,M3,M4,M5,F1,F2,F3,F4,F5"

    # Object storage for the clips themselves (MinIO in compose, any S3 API
    # elsewhere). Only metadata lives in Postgres. Names match the S3_* keys
    # already in .env.sample so an existing deployment needs no new variables;
    # clips are namespaced by the "clips/" key prefix rather than by a bucket
    # of their own.
    S3_ENDPOINT_URL: str = "http://minio:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "langup"
    S3_REGION: str = "us-east-1"

    # MP3 rather than the gateway's WAV: one 13-second clip is ~1.1 MB as
    # 44.1 kHz PCM but ~100 KB at 64 kbps mono — a 10x saving on both storage
    # and every playback. Speech at 64 kbps mono is transparent enough that the
    # difference is inaudible for single words and sentences.
    AUDIO_BITRATE: str = "64k"
    AUDIO_SAMPLE_RATE: int = 24000
    # ffmpeg must be on PATH (it is installed in the image).
    FFMPEG_BINARY: str = "ffmpeg"
    FFMPEG_TIMEOUT_SECONDS: float = 30.0

    # Mirrors the gateway's own cap: this is a word/sentence service, never an
    # article reader.
    AUDIO_MAX_TEXT_LENGTH: int = 400

    @property
    def available_voices(self) -> list[str]:
        return [v.strip() for v in self.AUDIO_AVAILABLE_VOICES.split(",") if v.strip()]

    @property
    def voice_map(self) -> dict[str, str]:
        """AUDIO_VOICES parsed into {language: voice}."""
        pairs = (item.split("=", 1) for item in self.AUDIO_VOICES.split(",") if "=" in item)
        return {lang.strip().lower(): voice.strip() for lang, voice in pairs}
