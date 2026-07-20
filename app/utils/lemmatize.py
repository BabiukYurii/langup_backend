# Dictionary lemmatization (simplemma): offline, deterministic, no LLM call.
import simplemma


def to_lemma(word: str, language: str) -> str:
    """Dictionary form of `word`, lowercased ("Occurs" -> "occur").

    Words the dictionary doesn't know come back unchanged (lowercased), and so
    does everything in a language simplemma has no data for — the shared
    `words` table then simply keeps the captured form, as it did before.
    """
    surface = word.strip().lower()
    try:
        return simplemma.lemmatize(surface, lang=language)
    except ValueError:  # unsupported language code
        return surface
