"""Detect the language of song lyrics, constrained to what the product supports.

Uses simplemma (already a dependency for lemmatization) — offline, deterministic,
no LLM call. Detection is scored against the supported set only, so a stray guess
can't tag a song with a language the app doesn't handle.
"""

import simplemma

from app.core.languages import SUPPORTED_LANGUAGES

# Below this top-language score the text is too mixed/uncertain to trust.
_MIN_SCORE = 0.5


def detect_language(text: str, min_score: float = _MIN_SCORE) -> str | None:
    """Best supported language for `text`, or None when uncertain/empty."""
    if not text or not text.strip():
        return None
    scores = simplemma.langdetect(text, lang=tuple(SUPPORTED_LANGUAGES))
    if not scores:
        return None
    lang, score = scores[0]
    return lang if score >= min_score else None
