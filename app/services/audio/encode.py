"""WAV -> the configured compressed format, and how long the result plays.

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
    """ffmpeg could not produce a clip (missing binary, bad input, timeout)."""


_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


async def clip_duration_ms(audio_bytes: bytes) -> int | None:
    """Playback length of the ENCODED clip.

    Measured on the encoded clip rather than read from the source WAV because
    encoding trims silence: the WAV's own length overstates a single word by
    more than half.

    Done by decoding to null with ffmpeg and reading the time it reports, not
    with ffprobe: over a pipe ffprobe cannot seek, so it answers "N/A" for a
    compressed stream's duration. This also keeps ffmpeg as the only binary we
    depend on. Runs on a cache miss only.
    """
    cfg = settings.audio
    # No -f on the input: ffmpeg probes it, so this works for whichever format
    # is configured without having to be told which.
    args = [cfg.FFMPEG_BINARY, "-hide_banner", "-i", "pipe:0", "-f", "null", "-"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(audio_bytes), timeout=cfg.FFMPEG_TIMEOUT_SECONDS)
        # Progress is reported repeatedly; the last line is the final length.
        matches = _TIME_RE.findall(stderr.decode(errors="replace"))
        if not matches:
            return None
        hours, minutes, seconds = matches[-1]
        return round((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)
    except Exception:  # noqa: BLE001 — metadata only; a clip must never fail over it
        logger.warning("Could not measure clip duration", exc_info=True)
        return None


async def transcode(wav_bytes: bytes) -> bytes:
    """Transcode WAV bytes to mono audio in the configured format."""
    cfg = settings.audio
    fmt = cfg.format
    # Each profile carries the rate that is actually transparent for speech in
    # its own codec; AUDIO_BITRATE overrides it when someone wants to tune.
    bitrate = cfg.AUDIO_BITRATE or fmt.bitrate
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
        bitrate,
        *(("-c:a", fmt.codec) if fmt.codec else ()),
        *fmt.extra_args,
        "-f",
        fmt.ffmpeg_format,
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
