# Spoken audio: where clips are stored and how they are encoded.
from dataclasses import dataclass

from app.core.config.base import BaseConfig


@dataclass(frozen=True)
class AudioFormat:
    """One encoding target: what ffmpeg is told, and how it is served."""

    name: str
    extension: str
    mime: str
    ffmpeg_format: str  # -f
    codec: str | None  # -c:a, None = the muxer's default
    bitrate: str
    extra_args: tuple[str, ...] = ()


AUDIO_FORMATS = {
    # Plays everywhere, including every iOS ever shipped. The baseline.
    "mp3": AudioFormat("mp3", ".mp3", "audio/mpeg", "mp3", None, "64k"),
    # AAC in a fragmented MP4. Same universal reach as mp3 — crucially it is
    # native on iOS, which Ogg is not — while measuring 32% smaller on a word
    # and 46% on a sentence. frag_keyframe+empty_moov is what lets MP4 be
    # written to a pipe at all: the normal muxer rewinds to patch the header,
    # which a pipe cannot do.
    "aac": AudioFormat(
        "aac",
        ".m4a",
        "audio/mp4",
        "mp4",
        "aac",
        "32k",
        ("-movflags", "frag_keyframe+empty_moov"),
    ),
    # The smallest of the three and the best codec for speech, but Safari only
    # learned Ogg in 17.4, and our failure mode is silent.
    "opus": AudioFormat("opus", ".ogg", "audio/ogg", "ogg", "libopus", "32k"),
}


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

    # Anything but the gateway's WAV: one 13-second clip is ~1.1 MB as 44.1 kHz
    # PCM but ~70 KB encoded.
    #
    # "mp3" is the default because it plays everywhere, and our failure mode is
    # silent — audio.js swallows errors, so a browser that cannot decode the
    # format shows a button that simply does nothing.
    #
    # "opus" (in Ogg) is measurably better: ~half the size at equal or better
    # speech quality (a word measured 6.2 KB as mp3@64k vs 2.9 KB as
    # opus@32k). The catch is Safari, which only learned to play Ogg Opus in
    # 17.4 — older iPhones would go quiet. Switch by setting AUDIO_FORMAT and
    # bumping nothing else: the format is part of the cache key, so clips
    # re-render under new keys and the old blobs become orphans the sweep
    # collects.
    AUDIO_FORMAT: str = "mp3"
    # Overrides the profile's own bitrate when set; empty means use the
    # profile's, since what is transparent differs sharply by codec.
    AUDIO_BITRATE: str = ""
    AUDIO_SAMPLE_RATE: int = 24000
    # ffmpeg must be on PATH (it is installed in the image).
    FFMPEG_BINARY: str = "ffmpeg"
    FFMPEG_TIMEOUT_SECONDS: float = 30.0

    # Mirrors the gateway's own cap: this is a word/sentence service, never an
    # article reader.
    AUDIO_MAX_TEXT_LENGTH: int = 400

    @property
    def format(self) -> "AudioFormat":
        """The encoding profile in force, falling back to mp3 if misconfigured."""
        return AUDIO_FORMATS.get(self.AUDIO_FORMAT.lower(), AUDIO_FORMATS["mp3"])

    @property
    def available_voices(self) -> list[str]:
        return [v.strip() for v in self.AUDIO_AVAILABLE_VOICES.split(",") if v.strip()]

    @property
    def voice_map(self) -> dict[str, str]:
        """AUDIO_VOICES parsed into {language: voice}."""
        pairs = (item.split("=", 1) for item in self.AUDIO_VOICES.split(",") if "=" in item)
        return {lang.strip().lower(): voice.strip() for lang, voice in pairs}
