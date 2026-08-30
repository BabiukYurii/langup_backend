"""Ф4: what the client needs in order to speak an exercise.

The rule about WHEN a type may be heard lives in practice.js, but it can only
be applied if the exercise says what language it is in — the page's own filter
is optional, so the exercise is the only reliable source. That contract is what
this file pins down.
"""

from app.enums.learning import ExerciseType
from app.schemas.exercise import ExerciseOut


class FakeExercise:
    """The fields ExerciseOut reads, without touching the database."""

    def __init__(self, exercise_type=ExerciseType.MULTIPLE_CHOICE.value, language="en", **kw):
        from datetime import datetime
        from uuid import uuid4

        self.uuid = uuid4()
        self.exercise_type = exercise_type
        self.prompt = "prompt"
        self.language = language
        self.difficulty = None
        self.payload = kw.get("payload", {"word": "resilient", "options": ["a", "b"]})
        self.answer = kw.get("answer", {"1": "resilient"})
        self.created_at = datetime.now()


def test_exercise_reports_its_language():
    """Without this the client cannot pick a voice: its own language filter may
    be unset, in which case the server chose the language."""
    out = ExerciseOut.from_exercise(FakeExercise(language="pl"))
    assert out.language == "pl"


def test_a_language_less_exercise_is_not_an_error():
    """Older rows predate the column; the client just renders no speaker."""
    assert ExerciseOut.from_exercise(FakeExercise(language=None)).language is None


def test_typing_still_hides_the_answer():
    """The speaker is withheld until the result screen precisely because the
    word is secret — serving it here would defeat both."""
    out = ExerciseOut.from_exercise(
        FakeExercise(
            exercise_type=ExerciseType.TYPING.value,
            payload={"text": "She was ___1___ about it."},
            answer={"1": "reluctant"},
        )
    )
    assert out.payload["length"] == len("reluctant")
    assert "reluctant" not in str(out.payload)


def test_fill_in_blanks_payload_carries_no_answer():
    """Same reason: the client can only build the spoken sentence after the
    server returns correct_answers with the attempt result."""
    out = ExerciseOut.from_exercise(
        FakeExercise(
            exercise_type=ExerciseType.FILL_IN_BLANKS.value,
            payload={"text": "He was ___1___ to sign.", "blanks": [{"index": 1, "options": ["eager"]}]},
            answer={"1": "reluctant"},
        )
    )
    assert "___1___" in out.payload["text"]
    assert "reluctant" not in str(out.payload)
