"""The cache key for a spoken clip.

Kept apart from the service so it stays pure and testable: this function decides
what counts as "the same clip", and every cache hit in the system depends on it
agreeing with itself across processes and restarts.
"""

import hashlib

from app.core import settings

# Bump when a change makes previously cached audio wrong — a new TTS engine, a
# different sample rate, a bitrate change. Old rows then simply stop being
# found and are re-synthesized, instead of being served as stale audio.
CACHE_VERSION = "v1"

# Where the learner's chosen voices live inside User.preferences — a blob
# shared with the exercise settings, so it is merged, never overwritten.
#
# A MAP of language -> voice, not one voice for the account: a learner studying
# English and Polish is listening to two different languages, and the voice that
# suits one has no bearing on the other.
VOICES_PREF_KEY = "tts_voices"

# The first cut stored a single voice for everything. Read for continuity so an
# account that set one keeps hearing it until a per-language choice replaces it.
LEGACY_VOICE_PREF_KEY = "tts_voice"


def normalize_text(text: str) -> str:
    """Collapse whitespace so trivially different requests share one clip."""
    return " ".join(text.split())


# What a sentence ends with. Word count alone cannot tell a sentence from a
# vocabulary entry — "go in one ear and out the other" is eight words and still
# a single thing to learn, read at normal speed — but a coursebook example
# sentence is punctuated and a dictionary phrase is not.
_SENTENCE_END = (".", "!", "?", "…")


def tempo_for(text: str) -> float:
    """How fast to read this back, as a multiple of the engine's own pace.

    Lives here rather than in the service because it feeds the cache key: two
    requests for the same words at different speeds are different clips, and
    whatever decides that has to be the same function in both places.
    """
    cfg = settings.audio
    cleaned = normalize_text(text)
    if not cleaned.endswith(_SENTENCE_END):
        return 1.0  # a phrase or a single word, however long
    if len(cleaned.split()) < cfg.AUDIO_SENTENCE_MIN_WORDS:
        return 1.0  # "Hi." is not what anybody is struggling to follow
    # atempo refuses anything outside this; a typo in .env should slow the
    # voice down, not break every clip.
    return min(2.0, max(0.5, cfg.AUDIO_SENTENCE_TEMPO))


def clip_hash(text: str, language: str, voice: str, tempo: float = 1.0) -> str:
    """Stable id for (text, language, voice) at a given speed.

    Case is preserved: capitalisation can change how a sentence is read, and a
    proper noun is not the same utterance as a common one.
    """
    # The format is part of the key: switching it must re-render rather than
    # serve an mp3 from a URL that now claims to be ogg. The blobs left under
    # the old keys become orphans, which the sweep collects.
    fmt = settings.audio.format.name
    payload = f"{CACHE_VERSION}|{normalize_text(text)}|{language.lower()}|{voice}|{fmt}"
    # Appended only when the speed is not the engine's own, so introducing a
    # sentence tempo re-renders sentences and leaves every single-word clip
    # exactly where it is — of 14,000 cached clips at the time, 134 were
    # sentences. Unconditional would have thrown the other 13,900 away.
    if tempo != 1.0:
        payload += f"|t{tempo:g}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def object_key(hash_: str, extension: str | None = None) -> str:
    """Storage path for a clip.

    Sharded by the first two hex characters: a flat prefix with hundreds of
    thousands of keys is slow to list and awkward to browse in the MinIO console.
    """
    return f"clips/{hash_[:2]}/{hash_}{extension or settings.audio.format.extension}"
