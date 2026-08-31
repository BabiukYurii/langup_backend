"""Transcoding against a real ffmpeg.

The service tests fake the encoder, so this is where the actual ffmpeg
invocation is checked: that it produces a playable MP3, that it strips the
silence Supertonic pads every utterance with, and that the reported duration
describes the ENCODED clip rather than the source.

Skipped where ffmpeg is not installed; the production image always has it.
"""

import math
import shutil
import struct
import wave
from io import BytesIO

import pytest

from app.core import settings
from app.services.audio.encode import AudioEncodingError, clip_duration_ms, transcode

pytestmark = pytest.mark.skipif(shutil.which(settings.audio.FFMPEG_BINARY) is None, reason="ffmpeg is not installed")


def tone_wav(seconds: float, lead_silence: float = 0.0, tail_silence: float = 0.0) -> bytes:
    """A sine tone, optionally wrapped in silence."""
    rate = 44100
    frames = []
    frames += [b"\x00\x00"] * int(rate * lead_silence)
    frames += [struct.pack("<h", int(20000 * math.sin(i * 0.05))) for i in range(int(rate * seconds))]
    frames += [b"\x00\x00"] * int(rate * tail_silence)
    buffer = BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"".join(frames))
    return buffer.getvalue()


async def test_produces_a_real_mp3():
    mp3 = await transcode(tone_wav(1.0))
    assert mp3[:3] in (b"ID3", b"\xff\xfb")  # ID3 tag or a raw MPEG frame


async def test_mp3_is_far_smaller_than_the_source_wav():
    """The whole point of transcoding: 44.1 kHz PCM is wasteful for one word."""
    wav = tone_wav(2.0)
    mp3 = await transcode(wav)
    assert len(mp3) < len(wav) / 5


async def test_padding_silence_is_trimmed():
    """Supertonic pads every clip; untrimmed, a single word is ~60% silence."""
    padded = tone_wav(0.6, lead_silence=0.4, tail_silence=0.6)
    duration = await clip_duration_ms(await transcode(padded))
    # 0.6s of tone plus the 0.1s kept at each end — nowhere near the 1.6s source.
    assert duration is not None
    assert 600 <= duration <= 1000


async def test_duration_describes_the_encoded_clip_not_the_source():
    long_tail = tone_wav(0.5, tail_silence=2.0)
    duration = await clip_duration_ms(await transcode(long_tail))
    assert duration is not None
    assert duration < 1500  # the 2s of trailing silence is gone


async def test_duration_of_garbage_is_none_not_an_error():
    """Duration is metadata — a clip must never fail over it."""
    assert await clip_duration_ms(b"not an mp3 at all") is None


async def test_a_missing_binary_is_reported_cleanly(monkeypatch):
    monkeypatch.setattr(settings.audio, "FFMPEG_BINARY", "definitely-not-a-real-binary")
    with pytest.raises(AudioEncodingError):
        await transcode(tone_wav(0.2))


# --- the format is a setting ----------------------------------------------


async def test_opus_is_produced_when_configured(monkeypatch):
    """Both profiles must actually encode, or the knob is a trap."""
    monkeypatch.setattr(settings.audio, "AUDIO_FORMAT", "opus")
    ogg = await transcode(tone_wav(1.0))
    assert ogg[:4] == b"OggS"  # Ogg page header


async def test_opus_is_materially_smaller_than_mp3(monkeypatch):
    """The reason the option exists at all."""
    wav = tone_wav(2.0)
    mp3 = await transcode(wav)
    monkeypatch.setattr(settings.audio, "AUDIO_FORMAT", "opus")
    ogg = await transcode(wav)
    assert len(ogg) < len(mp3)


async def test_duration_works_for_either_format(monkeypatch):
    """Duration is probed, not told, so it must not assume the container."""
    monkeypatch.setattr(settings.audio, "AUDIO_FORMAT", "opus")
    duration = await clip_duration_ms(await transcode(tone_wav(1.0)))
    assert duration is not None
    assert 900 <= duration <= 1300


def test_an_unknown_format_falls_back_to_mp3(monkeypatch):
    """A typo in the env must not leave the encoder without a target."""
    monkeypatch.setattr(settings.audio, "AUDIO_FORMAT", "flac-ish-nonsense")
    assert settings.audio.format.name == "mp3"


def test_the_key_extension_follows_the_format(monkeypatch):
    """Switching format must re-key, not serve an mp3 from an .ogg URL."""
    from app.services.audio.keys import clip_hash, object_key

    mp3_hash = clip_hash("apple", "en", "M1")
    assert object_key(mp3_hash).endswith(".mp3")

    monkeypatch.setattr(settings.audio, "AUDIO_FORMAT", "opus")
    opus_hash = clip_hash("apple", "en", "M1")
    assert opus_hash != mp3_hash  # the format is part of the cache key
    assert object_key(opus_hash).endswith(".ogg")
