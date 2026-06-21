from app.enums.base import BaseStrEnum


class PartOfSpeech(BaseStrEnum):
    NOUN = "NOUN"
    VERB = "VERB"
    ADJECTIVE = "ADJECTIVE"
    ADVERB = "ADVERB"
    PRONOUN = "PRONOUN"
    PREPOSITION = "PREPOSITION"
    CONJUNCTION = "CONJUNCTION"
    INTERJECTION = "INTERJECTION"
    PHRASE = "PHRASE"
    OTHER = "OTHER"


class MasteryLevel(BaseStrEnum):
    NEW = "NEW"
    LEARNING = "LEARNING"
    REVIEW = "REVIEW"
    MASTERED = "MASTERED"


class SourceType(BaseStrEnum):
    WEB_PAGE = "WEB_PAGE"
    PDF = "PDF"
    MANUAL = "MANUAL"
