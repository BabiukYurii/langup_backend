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
