"""WAV -> MP3, and how long the result plays.

The gateway speaks 44.1 kHz PCM because that is what the model emits; storing
and serving that would be wasteful for what is almost always a single word. We
transcode once, on the way into the cache, so every later playback is small.

ffmpeg is driven as a subprocess over pipes rather than through a binding: it is
one call on a cache miss, and a pipe keeps the clip off the disk entirely.
"""

import asyncio
import logging
import wave
from io import BytesIO

from app.core import settings

logger = logging.getLogger(__name__)


class AudioEncodingError(RuntimeError):
    """ffmpeg could not produce an MP3 (missing binary, bad input, timeout)."""


def wav_duration_ms(wav_bytes: bytes) -> int | None:
    """Playback length of a WAV, or None if it cannot be parsed.

    Read from the source WAV rather than the MP3 because a WAV header states
    the frame count outright, while measuring an MP3 would mean decoding it.
    """
    try:
        with wave.open(BytesIO(wav_bytes)) as wav:
            rate = wav.getframerate()
            return round(wav.getnframes() / rate * 1000) if rate else None
    except Exception:  # noqa: BLE001 — duration is metadata; never fail a clip over it
        logger.warning("Could not read WAV duration", exc_info=True)
        return None


async def wav_to_mp3(wav_bytes: bytes) -> bytes:
    """Transcode WAV bytes to mono MP3 at the configured bitrate."""
    cfg = settings.audio
    args = [
        cfg.FFMPEG_BINARY,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "wav",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        str(cfg.AUDIO_SAMPLE_RATE),
        "-b:a",
        cfg.AUDIO_BITRATE,
        "-f",
        "mp3",
        "pipe:1",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise AudioEncodingError(f"{cfg.FFMPEG_BINARY} is not installed") from e

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(wav_bytes), timeout=cfg.FFMPEG_TIMEOUT_SECONDS)
    except TimeoutError as e:
        proc.kill()  # otherwise a wedged ffmpeg outlives the request
        await proc.wait()
        raise AudioEncodingError("ffmpeg timed out") from e

    if proc.returncode != 0:
        raise AudioEncodingError(f"ffmpeg failed ({proc.returncode}): {stderr.decode(errors='replace')[:200]}")
    if not stdout:
        raise AudioEncodingError("ffmpeg produced no audio")
    return stdout
