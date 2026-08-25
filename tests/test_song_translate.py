import pytest

from app.core.exc import AIProviderError
from app.schemas.ai import GeneratedTranslation
from app.schemas.playlist import UnknownWord
from app.services.songs.translate import translate_unknown_words

pytestmark = pytest.mark.asyncio


class _StubGen:
    """Echoes the context so we can assert the song line was passed as sentence."""

    def __init__(self) -> None:
        self.calls = []

    async def generate_translation(self, params):
        self.calls.append((params.word, params.sentence, params.source_language, params.target_language))
        return GeneratedTranslation(translation=f"{params.word}:{params.sentence}", model="stub")


class _FailGen:
    async def generate_translation(self, params):
        raise AIProviderError("gateway down")


async def test_translates_in_line_context():
    gen = _StubGen()
    words = [UnknownWord(lemma="asleep", example="Fall asleep tonight")]
    out = await translate_unknown_words(words, "en", "uk", gen)
    assert out[0].translation == "asleep:Fall asleep tonight"
    # the song line was passed as the sentence, and the languages threaded through
    assert gen.calls == [("asleep", "Fall asleep tonight", "en", "uk")]


async def test_missing_translation_is_none_not_error():
    words = [UnknownWord(lemma="x", example="line")]
    out = await translate_unknown_words(words, "en", "uk", _FailGen())
    assert out[0].translation is None  # degraded gracefully
