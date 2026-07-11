import json

import pytest

from app.core.exc import AIResponseValidationError
from app.schemas.ai import FillInBlankParams
from app.services.ai.client import AIClient
from app.services.ai.exercise_generation import ExerciseGenerationService

VALID_CONTENT = json.dumps(
    {
        "text": "She stayed ___1___ despite the setback.",
        "blanks": [{"index": 1, "answer": "resilient", "options": ["resilient", "fragile", "angry", "tired"]}],
    }
)


class FakeAIClient(AIClient):
    """Canned gateway reply; records the prompts it was called with."""

    def __init__(self, content: str = VALID_CONTENT) -> None:
        super().__init__(base_url="http://fake", api_key="test", timeout=1)
        self.content = content
        self.last_system: str | None = None
        self.last_user: str | None = None

    async def chat_json(self, system: str, user: str, temperature: float = 0.7) -> dict:
        self.last_system = system
        self.last_user = user
        return {"content": self.content, "model": "fake-model"}


PARAMS = FillInBlankParams(words=["resilient"], level="B1", language="en")


async def test_generate_fill_in_blank_parses_valid_output():
    fake = FakeAIClient()
    service = ExerciseGenerationService(fake)

    result = await service.generate_fill_in_blank(PARAMS)

    assert "___1___" in result.text
    assert result.blanks[0].answer == "resilient"
    assert result.model == "fake-model"
    # the prompt is built backend-side and contains the target word and level
    assert "resilient" in fake.last_user
    assert "B1" in fake.last_user


async def test_generate_rejects_non_json_output():
    service = ExerciseGenerationService(FakeAIClient(content="not json at all"))
    with pytest.raises(AIResponseValidationError):
        await service.generate_fill_in_blank(PARAMS)


async def test_generate_repairs_unblanked_text():
    # the model wrote the word in the text instead of the ___N___ placeholder
    raw = json.dumps(
        {
            "text": "Despite the setback, she remained Resilient and kept going.",
            "blanks": [{"index": 1, "answer": "resilient", "options": ["flexible", "obedient", "weak"]}],
        }
    )
    service = ExerciseGenerationService(FakeAIClient(content=raw))
    result = await service.generate_fill_in_blank(PARAMS)

    assert "___1___" in result.text
    assert "Resilient" not in result.text  # replaced case-insensitively
    assert "resilient" in result.blanks[0].options  # answer added to options


async def test_generate_rejects_blank_missing_from_text():
    # the REQUESTED word's blank has neither placeholder nor answer in the text — unrepairable
    bad = json.dumps({"text": "No placeholders here.", "blanks": [{"index": 1, "answer": "resilient", "options": []}]})
    service = ExerciseGenerationService(FakeAIClient(content=bad))
    with pytest.raises(AIResponseValidationError):
        await service.generate_fill_in_blank(PARAMS)


async def test_generate_drops_unplaceable_extra_blank():
    # the model invented a second blank ("student") that appears nowhere in the
    # text — drop it and keep the exercise for the requested word
    raw = json.dumps(
        {
            "text": "She stayed ___1___ despite the setback.",
            "blanks": [
                {"index": 1, "answer": "resilient", "options": ["resilient", "fragile", "angry"]},
                {"index": 2, "answer": "student", "options": ["student", "teacher", "doctor"]},
            ],
        }
    )
    service = ExerciseGenerationService(FakeAIClient(content=raw))
    result = await service.generate_fill_in_blank(PARAMS)

    assert [b.answer for b in result.blanks] == ["resilient"]
    assert "___2___" not in result.text


async def test_generate_keeps_repairable_extra_blank():
    # the extra blank's word is present in the text — repair and keep both blanks
    raw = json.dumps(
        {
            "text": "The student stayed ___1___ despite the setback.",
            "blanks": [
                {"index": 1, "answer": "resilient", "options": ["resilient", "fragile", "angry"]},
                {"index": 2, "answer": "student", "options": ["student", "teacher", "doctor"]},
            ],
        }
    )
    service = ExerciseGenerationService(FakeAIClient(content=raw))
    result = await service.generate_fill_in_blank(PARAMS)

    assert [b.answer for b in result.blanks] == ["resilient", "student"]
    assert "___2___" in result.text and "student" not in result.text


async def test_generate_rejects_blanks_of_wrong_words():
    # the model blanked random words instead of the requested ones
    bad = json.dumps(
        {
            "text": "The resilient ___1___ kept working.",
            "blanks": [{"index": 1, "answer": "team", "options": ["team", "city"]}],
        }
    )
    service = ExerciseGenerationService(FakeAIClient(content=bad))
    with pytest.raises(AIResponseValidationError):
        await service.generate_fill_in_blank(PARAMS)


async def test_generate_rejects_malformed_blanks():
    bad = json.dumps({"text": "A ___1___ b.", "blanks": [{"answer": "x"}]})  # missing index
    service = ExerciseGenerationService(FakeAIClient(content=bad))
    with pytest.raises(AIResponseValidationError):
        await service.generate_fill_in_blank(PARAMS)
