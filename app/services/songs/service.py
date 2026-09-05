"""Analyse one song for a user: lyrics -> language -> known/unknown words.

Translation is separate and lazy (per word, on click) so opening a song is fast
and we don't fire dozens of AI calls up front.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.exc import BadRequestException, ObjectNotFoundException
from app.database.postgres import get_session
from app.enums.vocabulary import MasteryLevel
from app.repositories.playlist import PlaylistRepository, PlaylistSongRepository
from app.repositories.user import UserRepository
from app.repositories.user_word import UserWordRepository
from app.repositories.word import WordRepository
from app.repositories.word_translation import WordTranslationRepository
from app.schemas.ai import TranslationParams
from app.schemas.playlist import (
    AnalyzedLyrics,
    PlaylistDetailOut,
    PlaylistOut,
    PlaylistSongOut,
)
from app.services.ai.exercise_generation import ExerciseGenerationService, get_exercise_generation_service
from app.services.lyrics import fetch_lyrics
from app.services.songs.analysis import analyze_lyrics
from app.services.songs.language import detect_language
from app.utils.lemmatize import to_lemma

logger = logging.getLogger(__name__)

# Machine-readable markers for the client.
LYRICS_NOT_FOUND = "lyrics_not_found"
LANGUAGE_UNKNOWN = "language_unknown"

# "I already know it": park the word far in the future so spaced repetition
# never surfaces it, while it still counts as known (turns green).
_KNOWN_INTERVAL_DAYS = 3650


class SongService:
    def __init__(self, session: AsyncSession, generator: ExerciseGenerationService) -> None:
        self.session = session
        self.user_words = UserWordRepository(session)
        self.users = UserRepository(session)
        self.words = WordRepository(session)
        self.playlists = PlaylistRepository(session)
        self.links = PlaylistSongRepository(session)
        self.translations = WordTranslationRepository(session)
        self.generator = generator

    # --- saved playlists ---------------------------------------------------

    async def list_playlists(self, user_id: int) -> list[PlaylistOut]:
        rows = await self.playlists.list_for_user(user_id)
        return [
            PlaylistOut(
                uuid=p.uuid, name=p.name, status=p.status, song_count=await self.links.count_for_playlist(p.uuid)
            )
            for p in rows
        ]

    async def playlist_detail(self, user_id: int, playlist_uuid: UUID) -> PlaylistDetailOut:
        playlist = await self.playlists.get_for_user(user_id, playlist_uuid)
        if not playlist:
            raise ObjectNotFoundException(playlist_uuid, "Playlist")
        # Languages the user is learning: the language they're studying plus any
        # already in their vocabulary. Songs in other languages are hidden — the
        # point is to understand songs in a language you're learning.
        learned = {lang for lang, _ in await self.user_words.languages_for_user(user_id)}
        user = await self.users.get_by_id(user_id)
        if user and user.target_language:
            learned.add(user.target_language)

        vocab_by_lang: dict[str, set[str]] = {}  # cache the user's lemmas per language
        songs: list[PlaylistSongOut] = []
        for _, song in await self.links.songs_for_playlist(playlist_uuid):
            # Skip songs not in a language the user learns (once we know the
            # language). Unanalysed songs (language None) are kept until analysed.
            if learned and song.language and song.language not in learned:
                continue
            unknown = None
            if song.language and song.lemmas is not None:
                if song.language not in vocab_by_lang:
                    states = await self.user_words.lemma_states_for_user(user_id, song.language)
                    vocab_by_lang[song.language] = set(states.keys())
                have = vocab_by_lang[song.language]
                unknown = sum(1 for lemma in song.lemmas if lemma not in have)
            songs.append(
                PlaylistSongOut(
                    song_uuid=song.uuid,
                    title=song.title,
                    artist=song.artist,
                    language=song.language,
                    unknown_count=unknown,
                    in_learned_language=bool(song.language and song.language in learned),
                )
            )
        return PlaylistDetailOut(uuid=playlist.uuid, name=playlist.name, status=playlist.status, songs=songs)

    async def delete_playlist(self, user_id: int, playlist_uuid: UUID) -> None:
        playlist = await self.playlists.get_for_user(user_id, playlist_uuid)
        if not playlist:
            raise ObjectNotFoundException(playlist_uuid, "Playlist")
        await self.playlists.delete_one(playlist)  # playlist_songs cascade

    async def add_word(self, user_id: int, lemma: str, language: str, known: bool) -> bool:
        """Add a song word to the user's vocabulary.

        known=True  -> mark it MASTERED and parked (they already know it; no
                       exercises, never scheduled for review).
        known=False -> a normal new word to learn; the caller then schedules the
                       exercise pool refill.
        Returns True when a UserWord was created, False when it already existed.
        """
        lemma = await self._dictionary_form(lemma, language)
        word = await self.words.get_by_lemma_language(lemma, language)
        if not word:
            word = await self.words.create_one({"lemma": lemma, "language": language})
        if await self.user_words.get_by_user_word(user_id, word.uuid):
            return False  # already in the user's dictionary — idempotent

        data = {"user_id": user_id, "word_uuid": word.uuid}
        if known:
            now = datetime.now(UTC).replace(tzinfo=None)
            data |= {
                "mastery_level": MasteryLevel.MASTERED.value,
                "interval_days": _KNOWN_INTERVAL_DAYS,
                "repetitions": 1,
                "due_at": now + timedelta(days=_KNOWN_INTERVAL_DAYS),
            }
        await self.user_words.create_one(data)
        return True

    async def analyze_track(self, user_id: int, title: str, artist: str) -> AnalyzedLyrics:
        lyrics = await fetch_lyrics(title, artist)
        if not lyrics:
            raise BadRequestException(LYRICS_NOT_FOUND)
        language = detect_language(lyrics)
        if not language:
            raise BadRequestException(LANGUAGE_UNKNOWN)
        states = await self.user_words.lemma_states_for_user(user_id, language)
        mastered = MasteryLevel.MASTERED.value
        known = {lemma for lemma, level in states.items() if level == mastered}
        learning = {lemma for lemma, level in states.items() if level != mastered}
        return analyze_lyrics(lyrics, language, known, learning)

    async def translate_in_context(self, user_id: int, word: str, line: str, language: str) -> str | None:
        """Translate one word (or phrasal verb) using its song line as context.

        `word` is the surface form as it appears in the lyrics — deliberately not
        our offline lemma, which can mangle a word ("straight" -> "stretch") and
        make the model translate something the learner never saw.

        Read through a shared cache. The answer turns on the word, the line and
        the two languages and never on who asked, so the first learner to tap a
        word pays the model and everyone after them reads a row. On one CPU that
        is the difference between a chorus costing twenty inferences and one —
        and it is what lets the same glosses be filled in ahead of time.
        """
        from app.core.exc import AIProviderError, AIResponseValidationError
        from app.services.learning.exercise_service import translation_language_for
        from app.services.learning.model_busy import mark_user_work

        target = await translation_language_for(self.session, user_id)
        cached = await self.translations.get_cached(word, language, target, line)
        if cached is not None:
            return cached
        # A miss means someone is watching a spinner: claim the model.
        await mark_user_work()
        try:
            result = await self.generator.generate_translation(
                TranslationParams(word=word, sentence=line or None, source_language=language, target_language=target)
            )
        except (AIProviderError, AIResponseValidationError) as e:
            logger.warning("Song word translation failed for %r: %s: %s", word, type(e).__name__, e)
            return None
        if result.translation:
            await self.translations.remember(word, language, target, line, result.translation)
        return result.translation

    async def _dictionary_form(self, surface: str, language: str) -> str:
        """Base form to store a song word under.

        Prefers the AI's lemma (what the capture flow uses, and far better than
        the offline lemmatizer, which can turn "straight" into "stretch"); falls
        back to offline lemmatization when analysis is off or unavailable.
        Multi-word phrasal verbs are stored as-is.
        """
        if " " in surface.strip():
            return surface.strip().lower()
        if settings.exercises.DETECT_LANGUAGE_ON_CAPTURE:
            from app.services.learning.model_busy import mark_user_work

            await mark_user_work()
            try:
                result = await self.generator.analyze_word(surface)
                if result.lemma:
                    return result.lemma.strip().lower()
            except Exception:  # noqa: BLE001 — analysis is best-effort
                logger.warning("Song lemma analysis failed for %r; using offline lemma", surface)
        return to_lemma(surface, language)


async def get_song_service(
    session: AsyncSession = Depends(get_session),
    generator: ExerciseGenerationService = Depends(get_exercise_generation_service),
) -> SongService:
    return SongService(session, generator)
