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


class ExerciseStatus(BaseStrEnum):
    # Pool lifecycle: pre-generated -> served to the user -> answered.
    READY = "READY"
    SERVED = "SERVED"
    COMPLETED = "COMPLETED"


class AttemptResult(BaseStrEnum):
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    SKIPPED = "SKIPPED"
