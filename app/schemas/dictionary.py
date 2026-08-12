from pydantic import BaseModel, Field, model_validator


class DictionaryEntry(BaseModel):
    word: str = Field(min_length=1, max_length=128)
    translation: str = Field(min_length=1, max_length=256)


class DictionaryImportRequest(BaseModel):
    # Language of the words being imported (e.g. "en").
    source_language: str = Field(min_length=2, max_length=8)
    # Language the translations are in (e.g. "uk").
    target_language: str = Field(default="uk", min_length=2, max_length=8)
    # Provide structured entries, OR raw text with one "word<sep>translation" per
    # line (separator auto-detected: tab, |, ;, =, " - "/" — ", or comma).
    entries: list[DictionaryEntry] | None = None
    raw_text: str | None = None
    # Messy raw_text? Let the LLM extract clean {word, translation} pairs instead
    # of the deterministic splitter. Slower; only needed for unstructured input.
    normalize: bool = False

    @model_validator(mode="after")
    def _one_source(self):
        if not self.entries and not (self.raw_text and self.raw_text.strip()):
            raise ValueError("Provide either 'entries' or 'raw_text'")
        return self


class DictionaryImportResult(BaseModel):
    # How many entries were accepted and queued for import.
    queued: int
    # Celery task id to poll for progress; None when it ran in-process (no worker).
    task_id: str | None = None


class DictionaryImportStatus(BaseModel):
    status: str  # pending | running | done | failed
    done: int | None = None  # chunks processed so far
    total: int | None = None  # total chunks
    created: int | None = None
    updated: int | None = None
