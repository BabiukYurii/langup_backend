"""Translate a song's unknown words in the context of the line they appear in.

The song line is passed as the sentence so the model picks the sense that fits
the lyric (idioms/slang are common in songs), not a generic dictionary gloss.
Best-effort: a word the model can't translate is left with translation=None and
simply shown without a gloss, never failing the whole analysis.
"""

import logging

from app.core.exc import AIProviderError, AIResponseValidationError
from app.schemas.ai import TranslationParams
from app.schemas.playlist import UnknownWord

logger = logging.getLogger(__name__)


async def translate_unknown_words(
    unknown: list[UnknownWord],
    source_language: str,
    target_language: str,
    generator,
) -> list[UnknownWord]:
    """Fill each unknown word's `translation` in-place, using its example line."""
    for word in unknown:
        try:
            result = await generator.generate_translation(
                TranslationParams(
                    word=word.lemma,
                    sentence=word.example,
                    source_language=source_language,
                    target_language=target_language,
                )
            )
            word.translation = result.translation
        except (AIProviderError, AIResponseValidationError) as e:
            logger.warning("Song translation failed for %r: %s: %s", word.lemma, type(e).__name__, e)
            word.translation = None
    return unknown
