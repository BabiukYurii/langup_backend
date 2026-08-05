import json

import pytest

from app.core.exc import AIResponseValidationError
from app.schemas.ai import FillInBlankParams, TranslationParams, WordExerciseParams
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


# --- multiple choice ---------------------------------------------------------

WORD_PARAMS = WordExerciseParams(word="resilient", level="B1", language="en")


def _mc(definition, distractors) -> str:
    return json.dumps({"definition": definition, "distractors": distractors})


async def test_multiple_choice_parses_valid_output():
    raw = _mc("able to recover quickly from difficulties", ["easy to break", "very loud", "full of light"])
    service = ExerciseGenerationService(FakeAIClient(content=raw))
    result = await service.generate_multiple_choice(WORD_PARAMS)

    assert result.definition == "able to recover quickly from difficulties"
    assert len(result.distractors) == 3
    assert result.model == "fake-model"


async def test_multiple_choice_rejects_definition_leaking_word():
    raw = _mc("being resilient in hard times", ["easy to break", "very loud", "full of light"])
    service = ExerciseGenerationService(FakeAIClient(content=raw))
    with pytest.raises(AIResponseValidationError):
        await service.generate_multiple_choice(WORD_PARAMS)


async def test_multiple_choice_filters_bad_distractors():
    # one distractor duplicates the definition, one leaks the word — both dropped
    raw = _mc(
        "able to recover quickly",
        ["ABLE TO RECOVER QUICKLY", "like a resilient person", "easy to break", "very loud"],
    )
    service = ExerciseGenerationService(FakeAIClient(content=raw))
    result = await service.generate_multiple_choice(WORD_PARAMS)

    assert result.distractors == ["easy to break", "very loud"]


async def test_multiple_choice_rejects_when_too_few_distractors_survive():
    raw = _mc("able to recover quickly", ["able to recover quickly", "resilient thing"])
    service = ExerciseGenerationService(FakeAIClient(content=raw))
    with pytest.raises(AIResponseValidationError):
        await service.generate_multiple_choice(WORD_PARAMS)


# --- flashcard ---------------------------------------------------------------


async def test_flashcard_parses_valid_output():
    raw = json.dumps({"definition": "able to recover quickly", "example": "She proved resilient after the storm."})
    service = ExerciseGenerationService(FakeAIClient(content=raw))
    result = await service.generate_flashcard(WORD_PARAMS)

    assert result.definition == "able to recover quickly"
    assert "resilient" in result.example


async def test_flashcard_drops_example_without_the_word():
    raw = json.dumps({"definition": "able to recover quickly", "example": "A sentence about nothing."})
    service = ExerciseGenerationService(FakeAIClient(content=raw))
    result = await service.generate_flashcard(WORD_PARAMS)

    assert result.example is None  # useless example dropped, card kept


# --- translations ------------------------------------------------------------


def _translation_params(sentence: str | None = None) -> TranslationParams:
    return TranslationParams(word="turnover", sentence=sentence, source_language="en", target_language="uk")


async def test_translation_parses_the_requested_shape():
    service = ExerciseGenerationService(FakeAIClient(content=json.dumps({"translation": "оборот"})))
    result = await service.generate_translation(_translation_params())

    assert result.translation == "оборот"
    assert result.model == "fake-model"


async def test_translation_repairs_a_differently_named_key():
    # the model answered with its own key; a lone string is unambiguous
    service = ExerciseGenerationService(FakeAIClient(content=json.dumps({"uk": "оборот"})))
    result = await service.generate_translation(_translation_params())

    assert result.translation == "оборот"


async def test_translation_rejects_an_echoed_source_word():
    service = ExerciseGenerationService(FakeAIClient(content=json.dumps({"translation": "Turnover"})))
    with pytest.raises(AIResponseValidationError):
        await service.generate_translation(_translation_params())


async def test_translation_rejects_empty_output():
    service = ExerciseGenerationService(FakeAIClient(content=json.dumps({"translation": "   "})))
    with pytest.raises(AIResponseValidationError):
        await service.generate_translation(_translation_params())


async def test_translation_prompt_uses_the_captured_sentence():
    # the sentence is what makes the model pick the staff sense of "turnover"
    fake = FakeAIClient(content=json.dumps({"translation": "плинність кадрів"}))
    sentence = "Companies are noticing larger turnover rates of millennials."
    await ExerciseGenerationService(fake).generate_translation(_translation_params(sentence))

    assert sentence in fake.last_user
    assert "Ukrainian" in fake.last_user  # codes are spelled out for the model


async def test_translation_prompt_without_a_sentence_is_still_valid():
    fake = FakeAIClient(content=json.dumps({"translation": "оборот"}))
    await ExerciseGenerationService(fake).generate_translation(_translation_params())

    assert "turnover" in fake.last_user
    assert "sentence" not in fake.last_user.lower()


async def test_flashcard_rejects_definition_leaking_word():
    raw = json.dumps({"definition": "resilient means strong", "example": "He is resilient."})
    service = ExerciseGenerationService(FakeAIClient(content=raw))
    with pytest.raises(AIResponseValidationError):
        await service.generate_flashcard(WORD_PARAMS)
