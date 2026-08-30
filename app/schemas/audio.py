from pydantic import BaseModel, Field

from app.core import settings


class AudioRequest(BaseModel):
    # A word, a phrase or one sentence — never an article.
    text: str = Field(min_length=1, max_length=settings.audio.AUDIO_MAX_TEXT_LENGTH)
    # Language the text is in; picks the voice and tells the model how to read it.
    language: str = Field(min_length=2, max_length=8)
    # Explicit voice, overriding the language default (used by the profile
    # picker to preview a voice before it is saved).
    voice: str | None = Field(default=None, max_length=32)


class AudioOut(BaseModel):
    # Where to play it from. Relative, so it works across environments.
    url: str
    hash: str
    voice: str
    duration_ms: int | None = None
    # Whether this request was served from the cache. Purely diagnostic — it
    # makes the cache's hit rate visible in the browser's network tab.
    cached: bool


class VoicesOut(BaseModel):
    # Every voice the learner may pick, and the one they currently use.
    voices: list[str]
    selected: str | None = None
    # What each language falls back to when nothing is chosen.
    defaults: dict[str, str]
