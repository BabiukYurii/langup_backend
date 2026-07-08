# Prompt templates for each AI task (helix-style: prompts live in the backend,
# the AI service is a dumb inference gateway).

FILL_IN_BLANK_SYSTEM = (
    "You are a language-learning exercise generator. Always respond with a single valid JSON object and nothing else."
)

FILL_IN_BLANK_USER = """\
Write a short coherent text (2-4 sentences) in {language} at CEFR level {level}
that naturally uses ALL of these words: {words}.

Then replace each of those words in the text with a placeholder ___N___
(N = 1, 2, ... in order of appearance).

The blanks must be EXACTLY the given words — one blank per given word.
Never blank any other word.

For every blank also provide 3 plausible but incorrect distractor options.

Respond with JSON exactly in this shape:
{{
  "text": "string with ___1___ placeholders",
  "blanks": [
    {{"index": 1, "answer": "word", "options": ["word", "d1", "d2", "d3"]}}
  ]
}}
"""


def build_fill_in_blank_prompt(words: list[str], level: str, language: str) -> str:
    return FILL_IN_BLANK_USER.format(words=", ".join(words), level=level, language=language)
