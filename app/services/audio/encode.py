"""WAV -> MP3, and how long the result plays.

The gateway speaks 44.1 kHz PCM because that is what the model emits; storing
and serving that would be wasteful for what is almost always a single word. We
transcode once, on the way into the cache, so every later playback is small.

ffmpeg is driven as a subprocess over pipes rather than through a binding: it is
one call on a cache miss, and a pipe keeps the clip off the disk entirely.
"""

import asyncio
import logging
import re

from app.core import settings

logger = logging.getLogger(__name__)


class AudioEncodingError(RuntimeError):
    """ffmpeg could not produce an MP3 (missing binary, bad input, timeout)."""


_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


async def mp3_duration_ms(mp3_bytes: bytes) -> int | None:
    """Playback length of the ENCODED clip.

    Measured on the MP3 rather than read from the source WAV because encoding
    trims silence: the WAV's own length overstates a single word by more than
    half.

    Done by decoding to null with ffmpeg and reading the time it reports, not
    with ffprobe: over a pipe ffprobe cannot seek, so it answers "N/A" for an
    MP3's duration. This also keeps ffmpeg as the only binary we depend on.
    Runs on a cache miss only.
    """
    cfg = settings.audio
    args = [cfg.FFMPEG_BINARY, "-hide_banner", "-f", "mp3", "-i", "pipe:0", "-f", "null", "-"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(mp3_bytes), timeout=cfg.FFMPEG_TIMEOUT_SECONDS)
        # Progress is reported repeatedly; the last line is the final length.
        matches = _TIME_RE.findall(stderr.decode(errors="replace"))
        if not matches:
            return None
        hours, minutes, seconds = matches[-1]
        return round((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)
    except Exception:  # noqa: BLE001 — metadata only; a clip must never fail over it
        logger.warning("Could not measure MP3 duration", exc_info=True)
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
        # Trim silence from both ends. Supertonic pads every utterance to a
        # fixed length, so a single word arrives as ~0.6s of speech inside a
        # 1.4s clip — measured 60% silence. Left alone that is a dead pause
        # after every tap, which is most of the experience when a learner
        # drills a word list. stop_periods=-1 clears trailing silence too, and
        # keeping 0.1s at each end stops a hard consonant being clipped.
        "-af",
        (
            "silenceremove="
            "start_periods=1:start_threshold=-50dB:start_silence=0.1:"
            "stop_periods=-1:stop_threshold=-50dB:stop_silence=0.1"
        ),
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
