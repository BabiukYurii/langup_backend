"""Whole sentences are read back slower than the engine says them.

Single words come out fine; the complaint is always about sentences, which the
engine runs together faster than a learner can follow in a language they are
still learning. atempo changes speed without touching pitch, so the voice slows
rather than deepens.

The cache key has to know: the same words at two speeds are two clips.
"""

import math
import shutil
import struct
import wave
from io import BytesIO

import pytest

from app.core import settings
from app.services.audio.encode import clip_duration_ms, transcode
from app.services.audio.keys import clip_hash, tempo_for

WORD = "resilient"
PHRASE = "have a go at something"
SENTENCE = "She stayed resilient through every setback that year."


# --- who gets slowed down --------------------------------------------------


def test_a_single_word_is_left_alone():
    assert tempo_for(WORD) == 1.0


def test_a_vocabulary_phrase_is_left_alone_however_long():
    """Length cannot decide this. Both of these are single things to learn, and
    the longer one has more words than most example sentences."""
    assert tempo_for(PHRASE) == 1.0
    assert tempo_for("go in one ear and out the other") == 1.0


def test_a_sentence_is_slowed():
    assert tempo_for(SENTENCE) == settings.audio.AUDIO_SENTENCE_TEMPO
    assert tempo_for(SENTENCE) < 1.0


def test_the_length_threshold_is_where_the_setting_says(monkeypatch):
    monkeypatch.setattr(settings.audio, "AUDIO_SENTENCE_MIN_WORDS", 3)
    assert tempo_for("One two.") == 1.0
    assert tempo_for("One two three.") == settings.audio.AUDIO_SENTENCE_TEMPO


def test_punctuation_is_what_marks_a_sentence():
    long_phrase = "one two three four five six seven"
    assert tempo_for(long_phrase) == 1.0
    assert tempo_for(long_phrase + ".") == settings.audio.AUDIO_SENTENCE_TEMPO


def test_a_tempo_of_one_disables_the_whole_thing(monkeypatch):
    monkeypatch.setattr(settings.audio, "AUDIO_SENTENCE_TEMPO", 1.0)
    assert tempo_for(SENTENCE) == 1.0


@pytest.mark.parametrize("configured, expected", [(0.1, 0.5), (9.0, 2.0)])
def test_an_impossible_setting_is_clamped(monkeypatch, configured, expected):
    """atempo refuses anything outside 0.5-2.0. A typo in .env should slow the
    voice down, not break every clip in the system."""
    monkeypatch.setattr(settings.audio, "AUDIO_SENTENCE_TEMPO", configured)
    assert tempo_for(SENTENCE) == expected


# --- the cache key ---------------------------------------------------------


def test_word_clips_keep_the_keys_they_already_have():
    """The load-bearing one. Of 14,071 cached clips when this went in, 13,937
    were words: putting the tempo in the key unconditionally would have thrown
    them all away and re-synthesised them one tap at a time."""
    assert clip_hash(WORD, "en", "M1", 1.0) == clip_hash(WORD, "en", "M1")


def test_the_same_sentence_at_two_speeds_is_two_clips():
    assert clip_hash(SENTENCE, "en", "M1", 0.9) != clip_hash(SENTENCE, "en", "M1", 1.0)


def test_changing_the_tempo_setting_re_renders_sentences(monkeypatch):
    slow = clip_hash(SENTENCE, "en", "M1", tempo_for(SENTENCE))
    monkeypatch.setattr(settings.audio, "AUDIO_SENTENCE_TEMPO", 0.8)
    assert clip_hash(SENTENCE, "en", "M1", tempo_for(SENTENCE)) != slow


# --- and it actually comes out slower --------------------------------------


def _tone(seconds: float) -> bytes:
    rate = 44100
    frames = [struct.pack("<h", int(20000 * math.sin(i * 0.05))) for i in range(int(rate * seconds))]
    buffer = BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(frames))
    return buffer.getvalue()


@pytest.mark.skipif(shutil.which(settings.audio.FFMPEG_BINARY) is None, reason="ffmpeg is not installed")
async def test_a_slowed_clip_plays_longer():
    wav = _tone(2.0)
    normal = await clip_duration_ms(await transcode(wav))
    slowed = await clip_duration_ms(await transcode(wav, 0.5))

    assert normal and slowed
    assert slowed > normal * 1.5  # half speed, allowing for the silence trim


@pytest.mark.skipif(shutil.which(settings.audio.FFMPEG_BINARY) is None, reason="ffmpeg is not installed")
async def test_the_default_tempo_changes_nothing():
    wav = _tone(1.0)
    assert await transcode(wav) == await transcode(wav, 1.0)
