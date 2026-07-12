# Fill-in-the-blank generation: build prompt -> AI gateway -> validate output.
import json
import re

from fastapi import Depends

from app.core.exc import AIResponseValidationError
from app.schemas.ai import (
    Blank,
    FillInBlankParams,
    GeneratedFillInBlank,
    GeneratedFlashcard,
    GeneratedMultipleChoice,
    WordExerciseParams,
)
from app.services.ai.client import AIClient, get_ai_client
from app.services.ai.prompts import (
    FILL_IN_BLANK_SYSTEM,
    FLASHCARD_SYSTEM,
    MULTIPLE_CHOICE_SYSTEM,
    build_fill_in_blank_prompt,
    build_flashcard_prompt,
    build_multiple_choice_prompt,
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
