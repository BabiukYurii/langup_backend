from app.enums.base import BaseStrEnum


class ExerciseType(BaseStrEnum):
    FILL_IN_BLANKS = "FILL_IN_BLANKS"
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    MATCH_PAIRS = "MATCH_PAIRS"
    TIMED_CHALLENGE = "TIMED_CHALLENGE"
    FLASHCARD = "FLASHCARD"
    SENTENCE_RECONSTRUCTION = "SENTENCE_RECONSTRUCTION"
    LISTENING = "LISTENING"
    AI_CONTEXTUAL = "AI_CONTEXTUAL"
    TYPING = "TYPING"  # type the missing word into its own captured sentence


# Types the pool can produce today; the rest of ExerciseType is planned surface.
# The pool rotates through these and the API only accepts these.
SUPPORTED_EXERCISE_TYPES = (
    ExerciseType.FILL_IN_BLANKS,
    ExerciseType.MULTIPLE_CHOICE,
    ExerciseType.FLASHCARD,
    ExerciseType.MATCH_PAIRS,
    ExerciseType.TYPING,
)


class ExerciseStatus(BaseStrEnum):
    # Pool lifecycle: pre-generated -> served to the user -> answered.
    READY = "READY"
    SERVED = "SERVED"
    COMPLETED = "COMPLETED"


class AttemptResult(BaseStrEnum):
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    SKIPPED = "SKIPPED"
