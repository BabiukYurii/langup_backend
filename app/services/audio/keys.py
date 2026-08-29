"""The cache key for a spoken clip.

Kept apart from the service so it stays pure and testable: this function decides
what counts as "the same clip", and every cache hit in the system depends on it
agreeing with itself across processes and restarts.
"""

import hashlib

# Bump when a change makes previously cached audio wrong — a new TTS engine, a
# different sample rate, a bitrate change. Old rows then simply stop being
# found and are re-synthesized, instead of being served as stale audio.
CACHE_VERSION = "v1"


def normalize_text(text: str) -> str:
    """Collapse whitespace so trivially different requests share one clip."""
    return " ".join(text.split())


def clip_hash(text: str, language: str, voice: str) -> str:
    """Stable id for (text, language, voice).

    Case is preserved: capitalisation can change how a sentence is read, and a
    proper noun is not the same utterance as a common one.
    """
    payload = f"{CACHE_VERSION}|{normalize_text(text)}|{language.lower()}|{voice}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def object_key(hash_: str) -> str:
    """Storage path for a clip.

    Sharded by the first two hex characters: a flat prefix with hundreds of
    thousands of keys is slow to list and awkward to browse in the MinIO console.
    """
    return f"clips/{hash_[:2]}/{hash_}.mp3"
