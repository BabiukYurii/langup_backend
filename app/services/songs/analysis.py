"""Turn plain lyrics into per-word known/unknown data.

Pure and offline (no DB, no AI): tokenize each line, drop "junk" (stopwords,
punctuation, numbers), lemmatize the rest, and mark each real word as `known`
(already in the learner's vocabulary) or `unknown`. The AI translation of the
unknown words is a separate step so this stays trivially testable.
"""

import re
from functools import lru_cache

import stopwordsiso

from app.schemas.playlist import AnalyzedLine, AnalyzedLyrics, AnalyzedToken, UnknownWord
from app.utils.lemmatize import to_lemma

# A word: letters (any script) with optional internal apostrophes ("don't", "l'ame").
_WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
_MIN_WORD_LEN = 2


@lru_cache(maxsize=16)
def _stopwords(language: str) -> frozenset[str]:
    try:
        return frozenset(stopwordsiso.stopwords(language))
    except Exception:  # noqa: BLE001 — a language without a list just means no stopwords
        return frozenset()


def _chunks(line: str):
    """Yield (surface, is_word) chunks in order, so the line can be rebuilt."""
    idx = 0
    for m in _WORD_RE.finditer(line):
        if m.start() > idx:
            yield line[idx : m.start()], False
        yield m.group(), True
        idx = m.end()
    if idx < len(line):
        yield line[idx:], False


def _is_junk(surface: str, lemma: str, stops: frozenset[str]) -> bool:
    return len(surface) < _MIN_WORD_LEN or surface.lower() in stops or lemma in stops


def analyze_lyrics(lyrics: str, language: str, known_lemmas: set[str]) -> AnalyzedLyrics:
    """Analyse `lyrics` against the learner's `known_lemmas` (lemmas they have)."""
    stops = _stopwords(language)
    lines: list[AnalyzedLine] = []
    unknown: dict[str, str] = {}  # lemma -> first example line

    for raw_line in lyrics.splitlines():
        tokens: list[AnalyzedToken] = []
        for surface, is_word in _chunks(raw_line):
            if not is_word:
                tokens.append(AnalyzedToken(surface=surface, status="skip"))
                continue
            lemma = to_lemma(surface, language)
            if _is_junk(surface, lemma, stops):
                tokens.append(AnalyzedToken(surface=surface, lemma=lemma, status="skip"))
            elif lemma in known_lemmas:
                tokens.append(AnalyzedToken(surface=surface, lemma=lemma, status="known"))
            else:
                tokens.append(AnalyzedToken(surface=surface, lemma=lemma, status="unknown"))
                unknown.setdefault(lemma, raw_line.strip())
        lines.append(AnalyzedLine(tokens=tokens))

    return AnalyzedLyrics(
        language=language,
        lines=lines,
        unknown=[UnknownWord(lemma=lemma, example=example) for lemma, example in unknown.items()],
    )
