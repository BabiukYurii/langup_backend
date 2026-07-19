# Internal AI request/response envelopes (backend <-> langup_ai gateway) and
# validated shapes of generated content.
from typing import Literal

from pydantic import BaseModel, Field

CEFRLevel = Literal["A1", "A2", "B1", "B2", "C1", "C2"]


class FillInBlankParams(BaseModel):
    words: list[str] = Field(min_length=1, max_length=10)
    level: CEFRLevel = "B1"
    language: str = "en"


class Blank(BaseModel):
    index: int  # position of the blank in the text: ___1___, ___2___, ...
    answer: str  # the word that fills the blank
    options: list[str] = Field(default_factory=list)  # distractors incl. the answer; empty = free input


class GeneratedFillInBlank(BaseModel):
    text: str  # text with ___N___ placeholders
    blanks: list[Blank]
    model: str  # which LLM produced it (for auditing/quality tracking)


class WordExerciseParams(BaseModel):
    # Single-word exercise generation (multiple-choice, flashcard).
    word: str = Field(min_length=1, max_length=128)
    level: CEFRLevel = "B1"
    language: str = "en"


class GeneratedMultipleChoice(BaseModel):
    definition: str  # the correct meaning, concise
    distractors: list[str] = Field(min_length=1)  # plausible but wrong meanings
    model: str


class GeneratedFlashcard(BaseModel):
    definition: str  # back side of the card
    example: str | None = None  # example sentence using the word
    model: str


class TranslationParams(BaseModel):
    # One word at a time, with the sentence it was captured in. Measured against
    # batching several words: the sentence lets the model pick the right sense
    # ("turnover" in an HR text is staff churn, not revenue), and batching a
    # word per sentence confuses it.
    word: str = Field(min_length=1, max_length=128)
    sentence: str | None = None
    source_language: str = "en"
    target_language: str = "uk"


class GeneratedTranslation(BaseModel):
    translation: str
    model: str
