# Translations of dictionary words, cached on the shared Word row.
#
# CPU inference is slow and `words` is a shared dictionary, so a lemma is
# translated once and then reused by every user and every exercise. Words are
# normally translated in the background right after capture, which keeps the AI
# off the critical path when an exercise is being built.
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exc import AIProviderError, AIResponseValidationError
from app.models import Word
from app.repositories.word import WordRepository
from app.repositories.word_context import WordContextRepository
from app.schemas.ai import TranslationParams
from app.services.ai.exercise_generation import ExerciseGenerationService

logger = logging.getLogger(__name__)


def cached_translation(word: Word, target_language: str) -> str | None:
    """Read a translation out of Word.definitions.

    Stored as a list of {"lang", "translation"} entries so the column keeps
    matching its declared `list[dict]` shape.
    """
    for entry in word.definitions or []:
        if isinstance(entry, dict) and entry.get("lang") == target_language:
            translation = (entry.get("translation") or "").strip()
            if translation:
                return translation
    return None


class TranslationService:
    def __init__(self, session: AsyncSession, generator: ExerciseGenerationService) -> None:
        self.words = WordRepository(session)
        self.contexts = WordContextRepository(session)
        self.generator = generator

    async def translate_word(self, word: Word, target_language: str) -> str | None:
        """Translation for one word: cached if known, generated otherwise.

        Returns None instead of raising when the AI service is unhappy — a
        missing translation costs one exercise, not the whole request.
        """
        cached = cached_translation(word, target_language)
        if cached:
            return cached

        # The sentence the learner met the word in decides which sense to use.
        sentence = await self.contexts.latest_sentence(word.uuid)
        try:
            generated = await self.generator.generate_translation(
                TranslationParams(
                    word=word.lemma,
                    sentence=sentence,
                    source_language=word.language,
                    target_language=target_language,
                )
            )
        except (AIProviderError, AIResponseValidationError) as e:
            logger.warning("Translation failed for %r: %s: %s", word.lemma, type(e).__name__, e)
            return None

        await self._cache(word, target_language, generated.translation)
        return generated.translation

    async def translate_words(self, words: list[Word], target_language: str) -> dict[str, str]:
        """Translations for several words, one call each for the uncached ones.

        Slower than batching, but batching a word-per-sentence measurably
        confused the model; after capture-time translation most words are
        already cached anyway.
        """
        translations: dict[str, str] = {}
        for word in words:
            translation = await self.translate_word(word, target_language)
            if translation:
                translations[word.lemma] = translation
        return translations

    async def _cache(self, word: Word, target_language: str, translation: str) -> None:
        entries = [
            e for e in (word.definitions or []) if not (isinstance(e, dict) and e.get("lang") == target_language)
        ]
        entries.append({"lang": target_language, "translation": translation})
        # Rebind the list so SQLAlchemy notices the JSON column changed.
        await self.words.update_one(word, {"definitions": entries})
