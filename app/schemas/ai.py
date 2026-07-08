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
