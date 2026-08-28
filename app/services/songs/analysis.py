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


# Language-agnostic interjections / onomatopoeia common in lyrics. They aren't
# real vocabulary, so they're skipped (rendered plain) rather than flagged as
# words to learn.
_INTERJECTIONS = frozenset(
    {
        "uh",
        "uhh",
        "uhhh",
        "huh",
        "oh",
        "ohh",
        "ohhh",
        "ah",
        "ahh",
        "ahhh",
        "aah",
        "ooh",
        "oooh",
        "yeah",
        "yea",
        "yeh",
        "yeahh",
        "hey",
        "heyy",
        "hmm",
        "hm",
        "mmm",
        "mm",
        "mhm",
        "la",
        "na",
        "da",
        "ba",
        "woo",
        "wooo",
        "woah",
        "whoa",
        "whoo",
        "whooo",
        "ay",
        "aye",
        "yo",
        "yoo",
        "nah",
        "ha",
        "haha",
        "hah",
        "wo",
        "ho",
        "ugh",
        "eh",
        "ehh",
        "ow",
        "oi",
        "yah",
        "gah",
        "argh",
    }
)


# Phrasal verbs kept as ONE unit, so "float up" is translated as the phrase it
# is instead of a verb plus a stray particle. Stored as exact pairs (not
# "any verb + any particle") because without part-of-speech tagging a broad rule
# glues innocent pairs together — e.g. the noun in "the tears on your face".
_PHRASAL_VERBS = frozenset(
    {
        "back up",
        "beat up",
        "blow up",
        "break down",
        "break up",
        "bring back",
        "bring down",
        "bring up",
        "burn down",
        "burn out",
        "call back",
        "call off",
        "call out",
        "calm down",
        "carry on",
        "carry out",
        "catch up",
        "check in",
        "check out",
        "cheer up",
        "chill out",
        "clean up",
        "come back",
        "come down",
        "come in",
        "come on",
        "come out",
        "come over",
        "come through",
        "cool down",
        "count on",
        "cut off",
        "cut out",
        "die out",
        "do over",
        "drag on",
        "dress up",
        "drift away",
        "drop off",
        "drop out",
        "end up",
        "fade away",
        "fall apart",
        "fall back",
        "fall down",
        "fall out",
        "fall over",
        "figure out",
        "fill in",
        "fill out",
        "fill up",
        "find out",
        "float up",
        "get away",
        "get back",
        "get down",
        "get in",
        "get off",
        "get on",
        "get out",
        "get over",
        "get through",
        "get up",
        "give away",
        "give back",
        "give in",
        "give out",
        "give up",
        "go around",
        "go away",
        "go back",
        "go down",
        "go off",
        "go on",
        "go out",
        "go over",
        "go through",
        "grow up",
        "hang on",
        "hang out",
        "hang up",
        "hold back",
        "hold on",
        "hold out",
        "hold up",
        "keep away",
        "keep on",
        "keep out",
        "keep up",
        "knock down",
        "knock out",
        "let down",
        "let go",
        "let in",
        "let out",
        "lift up",
        "light up",
        "live on",
        "look around",
        "look back",
        "look down",
        "look out",
        "look through",
        "look up",
        "make out",
        "make up",
        "move on",
        "move out",
        "pass away",
        "pass out",
        "pay back",
        "pay off",
        "pick up",
        "pull away",
        "pull back",
        "pull off",
        "pull out",
        "pull over",
        "pull up",
        "push away",
        "push back",
        "push through",
        "put away",
        "put back",
        "put down",
        "put off",
        "put on",
        "put out",
        "put up",
        "reach out",
        "ride out",
        "rise up",
        "roll over",
        "run away",
        "run off",
        "run out",
        "sell out",
        "send off",
        "set off",
        "set out",
        "set up",
        "settle down",
        "show off",
        "show up",
        "shut down",
        "shut off",
        "shut out",
        "shut up",
        "sing along",
        "sit back",
        "sit down",
        "sit up",
        "slip away",
        "slow down",
        "speak out",
        "speak up",
        "speed up",
        "stand back",
        "stand out",
        "stand up",
        "start over",
        "stay away",
        "stay on",
        "stay out",
        "stay up",
        "step back",
        "step out",
        "step up",
        "stick around",
        "stick out",
        "stick together",
        "stick up",
        "take away",
        "take back",
        "take down",
        "take in",
        "take off",
        "take out",
        "take over",
        "take up",
        "talk back",
        "tear apart",
        "tear down",
        "tear up",
        "think back",
        "think over",
        "throw away",
        "throw out",
        "throw up",
        "turn around",
        "turn away",
        "turn back",
        "turn down",
        "turn in",
        "turn off",
        "turn on",
        "turn out",
        "turn over",
        "turn up",
        "wake up",
        "walk away",
        "walk out",
        "warm up",
        "wash away",
        "watch out",
        "wear off",
        "wear out",
        "wipe out",
        "work out",
        "write down",
    }
)


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
    low = surface.lower()
    if " " in low:  # a merged phrasal verb is always worth learning
        return False
    return len(surface) < _MIN_WORD_LEN or low in _INTERJECTIONS or low in stops or lemma in stops


def _units(line: str, language: str):
    """Yield (surface, lemma_or_None) units, phrasal verbs merged into one.

    A verb from _PHRASAL_VERBS directly followed by a particle ("float up") is
    emitted as a single unit so it can be translated as the phrase it is, not as
    two unrelated words. lemma is None for non-word chunks.
    """
    chunks = list(_chunks(line))
    i = 0
    while i < len(chunks):
        surface, is_word = chunks[i]
        if not is_word:
            yield surface, None
            i += 1
            continue
        lemma = to_lemma(surface, language)
        # verb + <space> + particle ?
        if i + 2 < len(chunks) and not chunks[i + 1][1] and chunks[i + 1][0].isspace() and chunks[i + 2][1]:
            particle = chunks[i + 2][0]
            pair = f"{lemma} {particle.lower()}"
            if pair in _PHRASAL_VERBS:
                yield f"{surface}{chunks[i + 1][0]}{particle}", pair
                i += 3
                continue
        yield surface, lemma
        i += 1


def content_lemmas(lyrics: str, language: str) -> list[str]:
    """Deduped content-word lemmas of `lyrics` (junk/stopwords removed).

    User-independent, so it can be cached on the shared Song row; a per-user
    unknown count is then just this set minus the user's vocabulary.
    """
    stops = _stopwords(language)
    seen: dict[str, None] = {}  # ordered set
    for raw_line in lyrics.splitlines():
        for surface, lemma in _units(raw_line, language):
            if lemma is None:
                continue
            if not _is_junk(surface, lemma, stops):
                seen.setdefault(lemma, None)
    return list(seen)


def analyze_lyrics(
    lyrics: str,
    language: str,
    known_lemmas: set[str],
    learning_lemmas: set[str] | None = None,
) -> AnalyzedLyrics:
    """Analyse `lyrics` against the learner's vocabulary.

    known_lemmas    -> mastered words (green).
    learning_lemmas -> words in their vocabulary still being learned (amber).
    Anything else that is a real word is unknown (red).
    """
    learning_lemmas = learning_lemmas or set()
    stops = _stopwords(language)
    lines: list[AnalyzedLine] = []
    unknown: dict[str, str] = {}  # lemma -> first example line

    for raw_line in lyrics.splitlines():
        tokens: list[AnalyzedToken] = []
        for surface, lemma in _units(raw_line, language):
            if lemma is None:
                tokens.append(AnalyzedToken(surface=surface, status="skip"))
                continue
            if _is_junk(surface, lemma, stops):
                tokens.append(AnalyzedToken(surface=surface, lemma=lemma, status="skip"))
            elif lemma in known_lemmas:
                tokens.append(AnalyzedToken(surface=surface, lemma=lemma, status="known"))
            elif lemma in learning_lemmas:
                tokens.append(AnalyzedToken(surface=surface, lemma=lemma, status="learning"))
            else:
                tokens.append(AnalyzedToken(surface=surface, lemma=lemma, status="unknown"))
                unknown.setdefault(lemma, raw_line.strip())
        lines.append(AnalyzedLine(tokens=tokens))

    return AnalyzedLyrics(
        language=language,
        lines=lines,
        unknown=[UnknownWord(lemma=lemma, example=example) for lemma, example in unknown.items()],
    )
