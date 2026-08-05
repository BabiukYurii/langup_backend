# Fill-in-the-blank generation: build prompt -> AI gateway -> validate output.
import json
import re

from fastapi import Depends

from app.core.exc import AIResponseValidationError
from app.core.languages import is_supported
from app.schemas.ai import (
    Blank,
    FillInBlankParams,
    GeneratedFillInBlank,
    GeneratedFlashcard,
    GeneratedMultipleChoice,
    GeneratedTranslation,
    TranslationParams,
    WordExerciseParams,
)
from app.services.ai.client import AIClient, get_ai_client
from app.services.ai.prompts import (
    FILL_IN_BLANK_SYSTEM,
    FLASHCARD_SYSTEM,
    MULTIPLE_CHOICE_SYSTEM,
    TRANSLATION_SYSTEM,
    WORD_ANALYSIS_SYSTEM,
    build_fill_in_blank_prompt,
    build_flashcard_prompt,
    build_multiple_choice_prompt,
    build_translation_prompt,
    build_word_analysis_prompt,
)

# Low temperature: exercises need format compliance, not creative writing.
_GENERATION_TEMPERATURE = 0.4


class ExerciseGenerationService:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai

    async def generate_fill_in_blank(self, params: FillInBlankParams) -> GeneratedFillInBlank:
        user_prompt = build_fill_in_blank_prompt(params.words, params.level, params.language)
        reply = await self.ai.chat_json(FILL_IN_BLANK_SYSTEM, user_prompt, temperature=_GENERATION_TEMPERATURE)
        return self._parse(reply, params.words)

    async def generate_multiple_choice(self, params: WordExerciseParams) -> GeneratedMultipleChoice:
        user_prompt = build_multiple_choice_prompt(params.word, params.level, params.language)
        reply = await self.ai.chat_json(MULTIPLE_CHOICE_SYSTEM, user_prompt, temperature=_GENERATION_TEMPERATURE)
        result = _parse_as(reply, GeneratedMultipleChoice)
        return _normalize_multiple_choice(result, params.word)

    async def generate_flashcard(self, params: WordExerciseParams) -> GeneratedFlashcard:
        user_prompt = build_flashcard_prompt(params.word, params.level, params.language)
        reply = await self.ai.chat_json(FLASHCARD_SYSTEM, user_prompt, temperature=_GENERATION_TEMPERATURE)
        result = _parse_as(reply, GeneratedFlashcard)
        return _normalize_flashcard(result, params.word)

    async def generate_translation(self, params: TranslationParams) -> GeneratedTranslation:
        user_prompt = build_translation_prompt(
            params.word, params.source_language, params.target_language, params.sentence
        )
        # Translation is a lookup, not a creative task — keep it near-deterministic.
        reply = await self.ai.chat_json(TRANSLATION_SYSTEM, user_prompt, temperature=0.1)
        return _normalize_translation(_parse_translation(reply), params.word)

    async def analyze_word(self, word: str, sentence: str | None = None) -> tuple[str | None, str | None]:
        """A captured word's (language, dictionary base form).

        language is None for anything outside the supported set, so a stray guess
        can't create a word under a language the product doesn't handle. lemma is
        None when the model gives nothing usable, so the caller can fall back to
        offline lemmatization. The AI base form is far better than a rule-based
        lemmatizer for inflected languages (Polish "barki" -> "bark").
        """
        prompt = build_word_analysis_prompt(word, sentence)
        reply = await self.ai.chat_json(WORD_ANALYSIS_SYSTEM, prompt, temperature=0.0)
        try:
            payload = json.loads(reply["content"])
            code = str(payload.get("language", "")).strip().lower()[:2]
            lemma = str(payload.get("lemma", "")).strip()
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None, None
        return (code if is_supported(code) else None), (lemma or None)

    @staticmethod
    def _parse(reply: dict, words: list[str]) -> GeneratedFillInBlank:
        try:
            payload = json.loads(reply["content"])
            blanks = [Blank.model_validate(b) for b in payload["blanks"]]
            result = GeneratedFillInBlank(text=payload["text"], blanks=blanks, model=reply.get("model", ""))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise AIResponseValidationError(f"Cannot parse model output: {e}") from e
        return _normalize(result, words)


def _parse_as(reply: dict, model_cls):
    try:
        payload = json.loads(reply["content"])
        return model_cls.model_validate({**payload, "model": reply.get("model", "")})
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        raise AIResponseValidationError(f"Cannot parse model output: {e}") from e


def _contains_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}", text, re.IGNORECASE) is not None


def _normalize_multiple_choice(result: GeneratedMultipleChoice, word: str) -> GeneratedMultipleChoice:
    """The correct definition must not leak the word itself, and distractors
    must be distinct from it (the 7B model occasionally paraphrases the same
    meaning twice)."""
    definition = result.definition.strip()
    if not definition:
        raise AIResponseValidationError("Empty definition")
    if _contains_word(definition, word):
        raise AIResponseValidationError(f"Definition leaks the word {word!r}")

    distractors = []
    for d in result.distractors:
        d = d.strip()
        if d and d.lower() != definition.lower() and not _contains_word(d, word):
            distractors.append(d)
    if len(distractors) < 2:
        raise AIResponseValidationError("Not enough usable distractors")

    result.definition = definition
    result.distractors = distractors[:3]
    return result


def _parse_translation(reply: dict) -> GeneratedTranslation:
    """Accept the requested shape and the loose ones small models fall into.

    Asked for {"translation": "..."} an 8B model sometimes answers with a
    different key, or wraps the word instead. Any single string value is
    unambiguous enough to use.
    """
    try:
        payload = json.loads(reply["content"])
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise AIResponseValidationError(f"Cannot parse model output: {e}") from e

    if not isinstance(payload, dict):
        raise AIResponseValidationError(f"Expected a JSON object, got {type(payload).__name__}")

    value = payload.get("translation")
    if not isinstance(value, str):
        strings = [v for v in payload.values() if isinstance(v, str) and v.strip()]
        if len(strings) != 1:
            raise AIResponseValidationError("No single translation in model output")
        value = strings[0]
    return GeneratedTranslation(translation=value, model=reply.get("model", ""))


def _normalize_translation(result: GeneratedTranslation, word: str) -> GeneratedTranslation:
    """An echoed source word is not a translation."""
    translation = result.translation.strip().strip('".')
    if not translation:
        raise AIResponseValidationError(f"Empty translation for {word!r}")
    if translation.lower() == word.lower():
        raise AIResponseValidationError(f"Model echoed the source word {word!r}")
    result.translation = translation
    return result


def _normalize_flashcard(result: GeneratedFlashcard, word: str) -> GeneratedFlashcard:
    """The definition must not leak the word; a broken example is dropped
    rather than failing the card."""
    definition = result.definition.strip()
    if not definition:
        raise AIResponseValidationError("Empty definition")
    if _contains_word(definition, word):
        raise AIResponseValidationError(f"Definition leaks the word {word!r}")

    result.definition = definition
    if result.example and not _contains_word(result.example, word):
        result.example = None  # example doesn't use the word — useless, drop it
    return result


def _normalize(result: GeneratedFillInBlank, words: list[str]) -> GeneratedFillInBlank:
    """Repair common 7B-model format slips instead of rejecting the answer.

    - The exercise must practice the requested words: every requested word has
      to be among the blank answers (the model sometimes blanks random words).
    - If a declared blank is absent from the text, blank out the first
      occurrence of the answer word ourselves.
    - Extra blanks the model invented on top of the requested words are kept if
      they are repairable, silently dropped otherwise — only problems with the
      requested words reject the whole exercise.
    - Make sure the correct answer is always present among the options.
    """
    requested = {w.lower() for w in words}
    answers = {b.answer.lower() for b in result.blanks}
    missing = [w for w in words if w.lower() not in answers]
    if missing:
        raise AIResponseValidationError(f"Requested words not blanked: {missing}")

    kept: list[Blank] = []
    for blank in result.blanks:
        placeholder = f"___{blank.index}___"
        if placeholder not in result.text:
            pattern = re.compile(rf"\b{re.escape(blank.answer)}\b", re.IGNORECASE)
            new_text, replaced = pattern.subn(placeholder, result.text, count=1)
            if not replaced:
                if blank.answer.lower() in requested:
                    raise AIResponseValidationError(
                        f"Blank ___{blank.index}___: neither placeholder nor answer {blank.answer!r} found in text"
                    )
                continue  # hallucinated extra blank — drop it, keep the exercise
            result.text = new_text

        if blank.options and not any(o.lower() == blank.answer.lower() for o in blank.options):
            blank.options.append(blank.answer)
        kept.append(blank)
    result.blanks = kept
    return result


async def get_exercise_generation_service(
    ai: AIClient = Depends(get_ai_client),
) -> ExerciseGenerationService:
    return ExerciseGenerationService(ai)
