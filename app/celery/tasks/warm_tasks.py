"""Preparing playlist songs before anyone opens them.

A learner who opens a song taps its red words one by one and waits for the model
each time. This module does that work ahead of them, in the gaps when nobody is
asking the model for anything.

Three rules shape everything here:

* The unit of work is a (song, target language) pair, never a (song, user) one.
  What a word means in a line does not depend on who is reading, so one pass
  serves every learner who shares that song and that language — and audio, keyed
  by voice alone, is shared wider still.
* The cache is the cursor. A run re-reads the song from the top and skips what
  is already stored, so an interrupted run loses nothing, a repeated run costs
  nothing, and no progress has to be written down.
* It always yields. Between words it checks whether a learner is waiting and
  whether its own budget is spent, and stops on either.
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.celery.config import celery_app
from app.core import settings

logger = logging.getLogger(__name__)


class WarmResult(BaseModel):
    """What one run got through, and why it stopped."""

    song: str = ""
    words_translated: int = 0
    clips_warmed: int = 0
    # Whether a full pass found nothing left to do. Only then does the pair stop
    # being handed out; anything else is resumed on a later tick.
    completed: bool = False
    # done | yielded | budget | capped | no_lyrics | disabled | idle
    reason: str = "idle"


@asynccontextmanager
async def _session() -> AsyncGenerator[AsyncSession]:
    """A session on an engine of this task's own (see ai_tasks for why)."""
    engine = create_async_engine(settings.db.url, connect_args=settings.db.connect_args, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()


def context_lines(analyzed) -> list[tuple[str, str]]:
    """Every candidate word with the line it sits in, in reading order.

    Two details decide whether any of this work is ever found again:

    * The line is rebuilt exactly as the reader builds it — the surfaces of ALL
      tokens joined with no separator, punctuation and spacing included. The
      tokenizer emits non-word chunks too, so this reproduces the original line.
      Build it any other way and the key differs from the one a tap looks up,
      and a whole night of work stays invisible.
    * Reading order, not frequency order. A song warmed only halfway is then
      instant exactly where a learner starts, rather than uniformly half-ready.
    """
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for line in analyzed.lines:
        text = "".join(token.surface for token in line.tokens)
        for token in line.tokens:
            # `unknown` here means "a real word that is not too common": the
            # analysis ran without a vocabulary, so this is the union of what
            # could be unknown to anyone. Words already in someone's vocabulary
            # were voiced when they were captured and need nothing from us.
            if token.status != "unknown":
                continue
            key = (token.surface.lower(), text)
            if key in seen:  # a chorus asks the same question many times over
                continue
            seen.add(key)
            pairs.append((token.surface, text))
    return pairs


async def _someone_is_waiting() -> bool:
    """Whether a learner is currently asking the gateway for something."""
    from app.services.learning.model_busy import model_is_busy

    return await model_is_busy()


async def _stop_reason(words_done: int, cap: int, started: float, budget: float) -> str | None:
    """Why this run should stop before the next word, or None to carry on.

    Checked between words rather than inside one: an inference cannot be
    interrupted, so one word is the finest grain of politeness available.
    """
    if words_done >= cap:
        return "capped"  # one long song must not take the whole night
    if time.monotonic() - started >= budget:
        return "budget"  # keep every task short, resume on the next tick
    if await _someone_is_waiting():
        return "yielded"  # someone is waiting: their tap beats our night work
    return None


# Words handed to the TTS gateway between two politeness checks. Small enough
# that a learner never waits long for the batch in flight to finish, large
# enough that the check is not most of the work.
_CLIP_BATCH = 10


async def _warm_clips_for(session: AsyncSession, candidate, words: list[str], warm_audio) -> int:
    """Speak the song's words in every voice its listeners actually chose.

    Synthesis is not inference, but it goes to the SAME gateway on the SAME
    machine — so it competes for the box a learner is waiting on just as surely,
    and gets the same treatment: batched, with a check between batches. An
    earlier version let this phase run unchecked on the theory that it "never
    touches the model"; the first live song spent two of its three and a half
    minutes here, unthrottled.

    Deduplicated by word, because a clip is keyed by (text, language, voice) and
    knows nothing about lines: a word appearing in five lines is one clip, not
    five lookups. Warming a voice nobody selected would cache clips no request
    ever looks up, hence the query; learners who never touched the setting are
    covered by the language default.
    """
    from app.services.songs.warm_scheduler import voices_for_song

    if warm_audio is None or not settings.audio.AUDIO_ENABLED:
        return 0
    unique = list(dict.fromkeys(words))  # reading order, one entry per word
    voices = await voices_for_song(session, candidate.song_uuid)
    default = settings.audio.voice_map.get(candidate.source_language.lower()[:2])
    warmed = 0
    for voice in {*voices, default} - {None}:
        for start in range(0, len(unique), _CLIP_BATCH):
            if await _someone_is_waiting():
                return warmed
            warmed += await warm_audio(unique[start : start + _CLIP_BATCH], candidate.source_language, voice)
    return warmed


async def warm_song(
    session: AsyncSession,
    candidate,
    generator,
    *,
    warm_audio: Callable[[list[str], str, str | None], Coroutine[Any, Any, int]] | None = None,
    budget_seconds: float | None = None,
    word_cap: int | None = None,
) -> WarmResult:
    """Prepare one (song, target language) pair, yielding to real work.

    Resumable with no bookkeeping: the translation cache is the cursor, so a run
    that stops early leaves the rest for the next tick, and one that runs twice
    does nothing the second time.
    """
    from app.core.exc import AIProviderError, AIResponseValidationError
    from app.repositories.word_translation import WordTranslationRepository
    from app.schemas.ai import TranslationParams
    from app.services.lyrics import fetch_lyrics
    from app.services.songs.analysis import analyze_lyrics

    budget = settings.warm.WARM_RUN_BUDGET_SECONDS if budget_seconds is None else budget_seconds
    cap = settings.warm.WARM_WORDS_PER_RUN if word_cap is None else word_cap
    result = WarmResult(song=f"{candidate.title} — {candidate.artist}".strip(" —"))

    lyrics = await fetch_lyrics(candidate.title, candidate.artist)
    if not lyrics:
        # The song was recorded as having lyrics, so this is a hiccup at the
        # source rather than a settled fact. Leave the pair open for another day.
        result.reason = "no_lyrics"
        return result

    # No vocabulary is passed: without a user there is nobody to already know a
    # word, so every real one comes back as a candidate — the union across all
    # readers, which is exactly what a shared cache should hold.
    analyzed = analyze_lyrics(lyrics, candidate.source_language, set(), set())
    pairs = context_lines(analyzed)

    translations = WordTranslationRepository(session)
    started = time.monotonic()
    done_all = True

    for surface, line in pairs:
        if await translations.get_cached(surface, candidate.source_language, candidate.target_language, line):
            continue  # already warm — this is the cursor
        stop = await _stop_reason(result.words_translated, cap, started, budget)
        if stop:
            result.reason, done_all = stop, False
            break
        try:
            generated = await generator.generate_translation(
                TranslationParams(
                    word=surface,
                    sentence=line or None,
                    source_language=candidate.source_language,
                    target_language=candidate.target_language,
                )
            )
        except (AIProviderError, AIResponseValidationError):
            logger.warning("Warm translation failed for %r", surface, exc_info=True)
            done_all = False
            continue
        if generated.translation:
            await translations.remember(
                surface, candidate.source_language, candidate.target_language, line, generated.translation
            )
            result.words_translated += 1

    if done_all:
        result.reason = "done"
        result.completed = True

    result.clips_warmed = await _warm_clips_for(session, candidate, [s for s, _ in pairs], warm_audio)
    return result


async def run_tick() -> WarmResult:
    """Pick the next song and prepare it. Shared by the task and its tests."""
    from app.celery.tasks.audio_tasks import warm_clips
    from app.repositories.song_warm_state import SongWarmStateRepository
    from app.services.ai.client import AIClient
    from app.services.ai.exercise_generation import ExerciseGenerationService
    from app.services.learning.model_busy import model_is_busy
    from app.services.songs.warm_scheduler import next_candidate

    if not settings.warm.WARM_ENABLED:
        return WarmResult(reason="disabled")
    # The cheapest check first: if a learner is mid-request, do not even spend a
    # query working out what we would have warmed.
    if await model_is_busy():
        return WarmResult(reason="yielded")

    async with _session() as session:
        candidate = await next_candidate(session)
        if candidate is None:
            return WarmResult(reason="idle")

        states = SongWarmStateRepository(session)
        # Stamped before the work, not after: a run that dies must still move the
        # rotation on, or one unwarmable song would be picked forever.
        await states.mark_attempted(candidate.song_uuid, candidate.target_language)

        generator = ExerciseGenerationService(AIClient())
        result = await warm_song(session, candidate, generator, warm_audio=warm_clips)

        if result.completed:
            await states.mark_completed(candidate.song_uuid, candidate.target_language, result.words_translated)
        elif result.words_translated:
            state = await states.get_or_create(candidate.song_uuid, candidate.target_language)
            await states.update_one(state, {"words_warmed": (state.words_warmed or 0) + result.words_translated})
        return result


@celery_app.task(name="warm.tick")
def warm_tick() -> dict:
    """One song, once a tick. Routed to the `warm` queue and its own worker."""
    result = asyncio.run(run_tick())
    if result.words_translated or result.clips_warmed:
        logger.info(
            "Warmed %s: %d translation(s), %d clip(s) [%s]",
            result.song,
            result.words_translated,
            result.clips_warmed,
            result.reason,
        )
    return result.model_dump()
