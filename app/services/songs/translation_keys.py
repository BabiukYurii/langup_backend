"""The cache key for one word translated inside a line.

Kept apart from the service so it stays pure and testable: this function decides
what counts as "the same translation", and every cache hit depends on it
agreeing with itself across processes and restarts.

The line itself is deliberately NOT part of what gets stored — only its hash.
A song's lyrics are fetched and parsed fresh on every read and never kept (see
the `Song` model, which stores lemmas and a language but no text). A cache that
held the example line for every word would quietly rebuild most of the text this
project takes care not to keep. Hashing gives the same cache key without the
copy.
"""

import hashlib

# Bump when a change makes previously cached translations wrong — a different
# model, a changed prompt, a new sense of "context". Old rows then simply stop
# being found and are re-translated, instead of being served as stale glosses.
CACHE_VERSION = "v1"


def normalize_word(word: str) -> str:
    """Fold a tapped surface form onto its cache key.

    Lowercased and whitespace-collapsed, so "Straight", "straight" and a stray
    double space all read the same row. Case carries no meaning for a gloss —
    unlike audio, where capitalisation can change how a line is spoken.
    """
    return " ".join(word.split()).lower()


def context_hash(line: str | None) -> str:
    """Stable id for the line a word was met in.

    An empty line is a key like any other: a word tapped outside a lyric still
    deserves a cached answer, just a different one from the same word inside a
    line that colours its sense.
    """
    payload = f"{CACHE_VERSION}|{' '.join((line or '').split()).lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
