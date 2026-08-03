# Prompt templates for each AI task (helix-style: prompts live in the backend,
# the AI service is a dumb inference gateway).

FILL_IN_BLANK_SYSTEM = (
    "You are a language-learning exercise generator. Always respond with a single valid JSON object and nothing else."
)

# Tuned for a small (7B) model: explicit blank count, a worked example and firm
# distractor rules — otherwise it tends to blank extra words or drift from the shape.
FILL_IN_BLANK_USER = """\
Write a short coherent text (2-3 sentences) in {language} at CEFR level {level}
that naturally uses each of these target words exactly once: {words}.

Then replace ONLY the target words with numbered placeholders ___1___, ___2___, ...
in order of appearance. The text must contain exactly {n_blanks} placeholder(s) —
one per target word. Every other word must stay untouched.

For each blank provide exactly 3 distractor options. Distractors must:
- be the same part of speech as the answer and fit the sentence grammatically,
- be clearly wrong in meaning in this context,
- NOT be synonyms of the answer.

Example for the single target word "reluctant":
{{
  "text": "He was ___1___ to sign the contract without reading it carefully first.",
  "blanks": [
    {{"index": 1, "answer": "reluctant", "options": ["reluctant", "eager", "visible", "frequent"]}}
  ]
}}

Now respond with one JSON object in exactly that shape for the target words: {words}.
"""


def build_fill_in_blank_prompt(words: list[str], level: str, language: str) -> str:
    return FILL_IN_BLANK_USER.format(words=", ".join(words), level=level, language=language, n_blanks=len(words))


MULTIPLE_CHOICE_SYSTEM = (
    "You are a language-learning exercise generator. Always respond with a single valid JSON object and nothing else."
)

MULTIPLE_CHOICE_USER = """\
For the {language} word "{word}" (CEFR level {level}):

1. Write ONE correct, concise definition (12 words maximum), understandable at level {level}.
2. Write EXACTLY 3 incorrect definitions. Each must:
   - be a real definition of some OTHER common {language} word (do not name that word),
   - have the same style and similar length as the correct one,
   - be clearly wrong for "{word}" — never a synonym or a close meaning.
3. Never use the word "{word}" or its forms inside any definition.

Example for the word "reluctant":
{{
  "definition": "unwilling to do something and hesitating about it",
  "distractors": [
    "feeling great happiness about a recent success",
    "able to be seen or noticed easily",
    "happening many times over a period"
  ]
}}

Now respond with one JSON object in exactly that shape for the word "{word}".
"""


def build_multiple_choice_prompt(word: str, level: str, language: str) -> str:
    return MULTIPLE_CHOICE_USER.format(word=word, level=level, language=language)


FLASHCARD_SYSTEM = (
    "You are a language-learning exercise generator. Always respond with a single valid JSON object and nothing else."
)

FLASHCARD_USER = """\
For the {language} word "{word}" (CEFR level {level}) provide:

1. "definition": one concise definition (12 words maximum), understandable at level {level}.
   Never use the word "{word}" or its forms inside the definition.
2. "example": one natural sentence (level {level}) that uses the word "{word}".

Example for the word "reluctant":
{{
  "definition": "unwilling to do something and hesitating about it",
  "example": "She was reluctant to lend him money again."
}}

Now respond with one JSON object in exactly that shape for the word "{word}".
"""


def build_flashcard_prompt(word: str, level: str, language: str) -> str:
    return FLASHCARD_USER.format(word=word, level=level, language=language)


# Language codes we can name explicitly in a prompt; anything else is passed
# through as-is (the model usually copes with the bare code).
LANGUAGE_NAMES = {
    "en": "English",
    "uk": "Ukrainian",
    "pl": "Polish",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
}


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code.lower(), code)


TRANSLATION_SYSTEM = "You are a bilingual dictionary. Always respond with a single valid JSON object and nothing else."

TRANSLATION_USER = """\
Translate the {source} word "{word}" into {target}.

Rules:
- Give the single most common translation, 1-3 words, no explanations.
- The translation must be in {target}, never in {source}.

Respond as {{"translation": "..."}}
"""

# Measured to be clearly better than translating a bare lemma: the sentence
# tells the model which sense is meant, so "turnover" in a text about staff
# comes out as personnel churn rather than as revenue or rotation.
TRANSLATION_CONTEXT_USER = """\
The {source} word "{word}" appears in this sentence:
"{sentence}"

Translate "{word}" into {target}, in the sense it carries there.

Rules:
- 1-3 words, no explanations.
- The translation must be in {target}, never in {source}.

Respond as {{"translation": "..."}}
"""


def build_translation_prompt(word: str, source_language: str, target_language: str, sentence: str | None = None) -> str:
    template = TRANSLATION_CONTEXT_USER if sentence else TRANSLATION_USER
    return template.format(
        word=word,
        sentence=sentence,
        source=language_name(source_language),
        target=language_name(target_language),
    )


# --- language detection ----------------------------------------------------
LANGUAGE_DETECTION_SYSTEM = (
    "You identify the language of a short text. Always respond with a single "
    "valid JSON object and nothing else."
)

LANGUAGE_DETECTION_USER = """\
What language is the word "{word}" written in? Use the surrounding sentence to decide:
"{sentence}"

Answer with its ISO 639-1 two-letter code, one of: uk, pl, en, de, es, fr, it, pt.

Respond as {{"language": "xx"}}
"""

LANGUAGE_DETECTION_WORD_ONLY = """\
What language is the word "{word}" written in?

Answer with its ISO 639-1 two-letter code, one of: uk, pl, en, de, es, fr, it, pt.

Respond as {{"language": "xx"}}
"""


def build_language_detection_prompt(word: str, sentence: str | None = None) -> str:
    template = LANGUAGE_DETECTION_USER if sentence else LANGUAGE_DETECTION_WORD_ONLY
    return template.format(word=word, sentence=sentence)
