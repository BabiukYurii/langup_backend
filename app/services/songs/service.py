"""Analyse one song for a user: lyrics -> language -> known/unknown words.

Translation is separate and lazy (per word, on click) so opening a song is fast
and we don't fire dozens of AI calls up front.
"""

import logging

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exc import BadRequestException
from app.database.postgres import get_session
from app.repositories.user_word import UserWordRepository
from app.schemas.ai import TranslationParams
from app.schemas.playlist import AnalyzedLyrics
from app.services.ai.exercise_generation import ExerciseGenerationService, get_exercise_generation_service
from app.services.lyrics import fetch_lyrics
from app.services.songs.analysis import analyze_lyrics
from app.services.songs.language import detect_language

logger = logging.getLogger(__name__)

# Machine-readable markers for the client.
LYRICS_NOT_FOUND = "lyrics_not_found"
LANGUAGE_UNKNOWN = "language_unknown"


class SongService:
    def __init__(self, session: AsyncSession, generator: ExerciseGenerationService) -> None:
        self.session = session
        self.user_words = UserWordRepository(session)
        self.generator = generator

    async def analyze_track(self, user_id: int, title: str, artist: str) -> AnalyzedLyrics:
        lyrics = await fetch_lyrics(title, artist)
        if not lyrics:
            raise BadRequestException(LYRICS_NOT_FOUND)
        language = detect_language(lyrics)
        if not language:
            raise BadRequestException(LANGUAGE_UNKNOWN)
        known = await self.user_words.lemmas_for_user(user_id, language)
        return analyze_lyrics(lyrics, language, known)

    async def translate_in_context(self, user_id: int, lemma: str, line: str, language: str) -> str | None:
        """Translate one word using the song line as context (lazy, on click)."""
        from app.core.exc import AIProviderError, AIResponseValidationError
        from app.services.learning.exercise_service import translation_language_for

        target = await translation_language_for(self.session, user_id)
        try:
            result = await self.generator.generate_translation(
                TranslationParams(word=lemma, sentence=line or None, source_language=language, target_language=target)
            )
        except (AIProviderError, AIResponseValidationError) as e:
            logger.warning("Song word translation failed for %r: %s: %s", lemma, type(e).__name__, e)
            return None
        return result.translation


async def get_song_service(
    session: AsyncSession = Depends(get_session),
    generator: ExerciseGenerationService = Depends(get_exercise_generation_service),
) -> SongService:
    return SongService(session, generator)
