# Fill-in-the-blank generation: build prompt -> AI gateway -> validate output.
import json
import re

from fastapi import Depends

from app.core.exc import AIResponseValidationError
from app.schemas.ai import Blank, FillInBlankParams, GeneratedFillInBlank
from app.services.ai.client import AIClient, get_ai_client
from app.services.ai.prompts import FILL_IN_BLANK_SYSTEM, build_fill_in_blank_prompt


class ExerciseGenerationService:
    def __init__(self, ai: AIClient) -> None:
        self.ai = ai

    async def generate_fill_in_blank(self, params: FillInBlankParams) -> GeneratedFillInBlank:
        user_prompt = build_fill_in_blank_prompt(params.words, params.level, params.language)
        reply = await self.ai.chat_json(FILL_IN_BLANK_SYSTEM, user_prompt)
        return self._parse(reply, params.words)

    @staticmethod
    def _parse(reply: dict, words: list[str]) -> GeneratedFillInBlank:
        try:
            payload = json.loads(reply["content"])
            blanks = [Blank.model_validate(b) for b in payload["blanks"]]
            result = GeneratedFillInBlank(text=payload["text"], blanks=blanks, model=reply.get("model", ""))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise AIResponseValidationError(f"Cannot parse model output: {e}") from e
        return _normalize(result, words)


def _normalize(result: GeneratedFillInBlank, words: list[str]) -> GeneratedFillInBlank:
    """Repair common 7B-model format slips instead of rejecting the answer.

    - The exercise must practice the requested words: every requested word has
      to be among the blank answers (the model sometimes blanks random words).
    - If a declared blank is absent from the text, blank out the first
      occurrence of the answer word ourselves.
    - Make sure the correct answer is always present among the options.
    """
    answers = {b.answer.lower() for b in result.blanks}
    missing = [w for w in words if w.lower() not in answers]
    if missing:
        raise AIResponseValidationError(f"Requested words not blanked: {missing}")

    for blank in result.blanks:
        placeholder = f"___{blank.index}___"
        if placeholder not in result.text:
            pattern = re.compile(rf"\b{re.escape(blank.answer)}\b", re.IGNORECASE)
            new_text, replaced = pattern.subn(placeholder, result.text, count=1)
            if not replaced:
                raise AIResponseValidationError(
                    f"Blank ___{blank.index}___: neither placeholder nor answer {blank.answer!r} found in text"
                )
            result.text = new_text

        if blank.options and not any(o.lower() == blank.answer.lower() for o in blank.options):
            blank.options.append(blank.answer)
    return result


async def get_exercise_generation_service(
    ai: AIClient = Depends(get_ai_client),
) -> ExerciseGenerationService:
    return ExerciseGenerationService(ai)
