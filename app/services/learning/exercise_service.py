# ExerciseService: serve exercises from a per-user pool, grade attempts (feeding
# the result into SM-2), and refill the pool via the AI generation service.
import logging
import random
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings
from app.core.exc import AIProviderError, AIResponseValidationError, BadRequestException, ObjectNotFoundException
from app.database.postgres import get_session
from app.enums.learning import SUPPORTED_EXERCISE_TYPES, AttemptResult, ExerciseStatus, ExerciseType
from app.models import UserWord
from app.repositories.exercise import ExerciseRepository
from app.repositories.exercise_attempt import ExerciseAttemptRepository
from app.repositories.user import UserRepository
from app.repositories.user_word import UserWordRepository
from app.repositories.word import WordRepository
from app.schemas.ai import FillInBlankParams, WordExerciseParams
from app.schemas.exercise import AttemptResultOut, ExerciseOut, ExercisePreferences, SubmitAttemptRequest
from app.services.ai.exercise_generation import ExerciseGenerationService, get_exercise_generation_service
from app.services.learning.spaced_repetition import SpacedRepetitionService
from app.services.vocabulary.translation_service import TranslationService

logger = logging.getLogger(__name__)

# Recall quality fed into SM-2 when an exercise is answered.
_QUALITY_CORRECT = 5
_QUALITY_INCORRECT = 2

# Types the pool rotates through when replenishing, unless the user narrowed
# the list in their preferences.
_TYPE_CYCLE = list(SUPPORTED_EXERCISE_TYPES)

# Key under which the enabled types live in User.preferences.
_PREF_KEY = "exercise_types"

# A flashcard is self-graded: the client submits whether the user knew the word.
FLASHCARD_KNOWN = "know"
FLASHCARD_UNKNOWN = "dont_know"


def _utcnow() -> datetime:
    # Naive UTC to match the DB's timezone-less DateTime columns.
    return datetime.now(UTC).replace(tzinfo=None)


class ExercisePoolService:
    def __init__(self, session: AsyncSession, generator: ExerciseGenerationService) -> None:
        self.session = session
        self.exercises = ExerciseRepository(session)
        self.attempts = ExerciseAttemptRepository(session)
        self.user_words = UserWordRepository(session)
        self.users = UserRepository(session)
        self.generator = generator
        self.translations = TranslationService(session, generator)
        self.words_repo = WordRepository(session)

    async def get_preferences(self, user_id: int) -> ExercisePreferences:
        """Enabled exercise types; every type is on until the user says otherwise."""
        user = await self.users.get_by_id(user_id)
        if not user:
            raise ObjectNotFoundException(user_id, "User")
        stored = (user.preferences or {}).get(_PREF_KEY)
        # Drop anything stale (a type that was dropped from the supported set)
        # so an old preference can never stall the pool.
        valid = [t for t in stored or [] if t in SUPPORTED_EXERCISE_TYPES]
        return ExercisePreferences(exercise_types=valid or _TYPE_CYCLE)

    async def set_preferences(self, user_id: int, prefs: ExercisePreferences) -> ExercisePreferences:
        user = await self.users.get_by_id(user_id)
        if not user:
            raise ObjectNotFoundException(user_id, "User")

        enabled = [t.value for t in prefs.exercise_types]
        # JSON column: rebind a new dict so SQLAlchemy sees the change.
        await self.users.update_one(user, {"preferences": {**(user.preferences or {}), _PREF_KEY: enabled}})

        # Pooled-but-unserved exercises of now-disabled types would occupy the
        # pool without ever being handed out — drop them so refills can work.
        disabled = [t for t in ExerciseType.list() if t not in enabled]
        await self.exercises.drop_ready_of_types(user_id, disabled)
        return ExercisePreferences(exercise_types=prefs.exercise_types)

    async def get_next(self, user_id: int, exercise_type: ExerciseType | None = None) -> ExerciseOut:
        """Hand out the next pending exercise (re-serving an unanswered one first)."""
        ex = await self.exercises.next_pending(user_id, exercise_type.value if exercise_type else None)
        if not ex:
            raise ObjectNotFoundException(None, "Exercise")
        if ex.status != ExerciseStatus.SERVED.value:
            await self.exercises.update_one(ex, {"status": ExerciseStatus.SERVED.value})
        return ExerciseOut.from_exercise(ex)

    async def submit_attempt(self, user_id: int, exercise_uuid: UUID, data: SubmitAttemptRequest) -> AttemptResultOut:
        ex = await self.exercises.get_for_user(user_id, exercise_uuid)
        if not ex:
            raise ObjectNotFoundException(exercise_uuid, "Exercise")
        if ex.status == ExerciseStatus.COMPLETED.value:
            raise BadRequestException("Exercise already answered")

        correct = {str(k): v for k, v in (ex.answer or {}).items()}
        matched = self._matched_keys(correct, data.answers)
        is_correct = len(matched) == len(correct) and not self._mistake_budget_blown(ex, data)
        result = AttemptResult.CORRECT if is_correct else AttemptResult.INCORRECT
        quality = _QUALITY_CORRECT if is_correct else _QUALITY_INCORRECT

        await self.attempts.create_one(
            {
                "user_id": user_id,
                "exercise_uuid": ex.uuid,
                "submitted_answer": data.answers,
                "result": result.value,
                "quality": quality,
                "score": len(matched),
                "response_time_ms": data.response_time_ms,
            }
        )
        await self.exercises.update_one(ex, {"status": ExerciseStatus.COMPLETED.value})

        if ex.exercise_type == ExerciseType.MATCH_PAIRS.value:
            # Many words in one round — grade each pair the user actually reached.
            mastery = await self._feed_pairs(user_id, ex, correct, data.answers)
        else:
            mastery = await self._feed_spaced_repetition(user_id, ex.word_uuid, quality)

        return AttemptResultOut(
            exercise_uuid=ex.uuid,
            result=result,
            is_correct=is_correct,
            correct_answers=correct,
            mastery_level=mastery,
        )

    async def replenish(self, user_id: int) -> int:
        """Top the pool back up to EXERCISE_POOL_TARGET unanswered exercises.

        Best-effort: words the AI service can't turn into a valid exercise are
        skipped rather than failing the whole refill. Returns how many were added.
        """
        need = settings.exercises.EXERCISE_POOL_TARGET - await self.exercises.count_pending(user_id)
        if need <= 0:
            return 0

        # Rotate the types the user enabled; offset by their total so the same
        # word gets different types across refills.
        cycle = (await self.get_preferences(user_id)).exercise_types
        _, total_ever = await self.exercises.get_many(user_id=user_id, limit=1)

        # One word feeds one single-word exercise; match-pairs pulls its own set.
        queue = await self._candidate_words(user_id, need)

        created = 0
        for i in range(need):
            ex_type = cycle[(total_ever + i) % len(cycle)]
            try:
                if ex_type == ExerciseType.MATCH_PAIRS:
                    built = await self._generate_match_pairs(user_id)
                elif queue:
                    await self._generate_and_store(user_id, queue.pop(0), ex_type)
                    built = True
                else:
                    built = False  # out of words for single-word types
            except (AIProviderError, AIResponseValidationError) as e:
                logger.warning("Skipping %s exercise: %s: %s", ex_type.value, type(e).__name__, e)
                continue
            created += int(built)
        return created

    async def _candidate_words(self, user_id: int, limit: int) -> list[UserWord]:
        # Words that are due for review first, then anything in the vocabulary.
        due = await self.user_words.list_due(user_id, _utcnow(), limit=limit)
        if due:
            return due
        rows, _ = await self.user_words.list_for_user(user_id, page=1, limit=limit)
        return rows

    async def _translation_language(self, user_id: int) -> str:
        return await translation_language_for(self.session, user_id)

    async def _generate_match_pairs(self, user_id: int) -> bool:
        """Build one match-pairs round out of several words. Returns False when
        there is not enough usable vocabulary — that is normal, not an error."""
        # A round is a whole session over many words, not a single card. Queuing
        # several at once would just repeat the same words, so keep one pending.
        if await self.exercises.has_pending_of_type(user_id, ExerciseType.MATCH_PAIRS.value):
            return False

        visible = settings.exercises.MATCH_PAIRS_VISIBLE
        user_words = await self._candidate_words(user_id, settings.exercises.MATCH_PAIRS_TOTAL)
        if len(user_words) < visible:
            logger.info("Not enough vocabulary for a match-pairs round (%d words)", len(user_words))
            return False

        target_language = await self._translation_language(user_id)
        translations = await self.translations.translate_words([uw.word for uw in user_words], target_language)

        pairs: list[dict] = []
        seen: set[str] = set()
        for uw in user_words:
            translation = translations.get(uw.word.lemma)
            # A repeated translation would make the round ambiguous — two cards
            # would both be "correct" for the same word.
            if not translation or translation.lower() in seen:
                continue
            seen.add(translation.lower())
            pairs.append(
                {
                    "id": len(pairs) + 1,
                    "word": uw.word.lemma,
                    "translation": translation,
                    "word_uuid": str(uw.word_uuid),
                }
            )

        if len(pairs) < visible:
            logger.info("Only %d usable pairs after translation — skipping match-pairs", len(pairs))
            return False

        await self.exercises.create_one(
            {
                "user_id": user_id,
                "word_uuid": None,  # a round spans many words
                "exercise_type": ExerciseType.MATCH_PAIRS.value,
                "status": ExerciseStatus.READY.value,
                "prompt": "Match each word with its translation.",
                "payload": {
                    "pairs": pairs,
                    "visible": visible,
                    "max_mistakes": settings.exercises.MATCH_PAIRS_MAX_MISTAKES,
                    "language": target_language,
                },
                "answer": {str(p["id"]): p["translation"] for p in pairs},
                "is_ai_generated": True,
            }
        )
        return True

    async def _generate_and_store(self, user_id: int, uw: UserWord, ex_type: ExerciseType) -> None:
        level = settings.exercises.EXERCISE_DEFAULT_LEVEL
        lemma, language = uw.word.lemma, uw.word.language

        if ex_type == ExerciseType.FILL_IN_BLANKS:
            generated = await self.generator.generate_fill_in_blank(
                FillInBlankParams(words=[lemma], level=level, language=language)
            )
            prompt = "Fill in the blanks with the correct word."
            payload = {
                "text": generated.text,
                "blanks": [{"index": b.index, "options": b.options} for b in generated.blanks],
            }
            answer = {str(b.index): b.answer for b in generated.blanks}
        elif ex_type == ExerciseType.MULTIPLE_CHOICE:
            generated = await self.generator.generate_multiple_choice(
                WordExerciseParams(word=lemma, level=level, language=language)
            )
            prompt = "Choose the correct meaning of the word."
            options = [generated.definition, *generated.distractors]
            random.shuffle(options)  # stored payload is client-facing — don't leak the answer position
            payload = {"word": lemma, "options": options}
            answer = {"1": generated.definition}
        elif ex_type == ExerciseType.FLASHCARD:
            generated = await self.generator.generate_flashcard(
                WordExerciseParams(word=lemma, level=level, language=language)
            )
            prompt = "Do you remember this word?"
            payload = {"front": lemma, "back": generated.definition, "example": generated.example}
            answer = {"1": FLASHCARD_KNOWN}
        else:  # pragma: no cover — cycle only contains the types above
            raise AIResponseValidationError(f"Unsupported exercise type {ex_type}")

        await self.exercises.create_one(
            {
                "user_id": user_id,
                "word_uuid": uw.word_uuid,
                "exercise_type": ex_type.value,
                "status": ExerciseStatus.READY.value,
                "prompt": prompt,
                "payload": payload,
                "answer": answer,
                "is_ai_generated": True,
            }
        )

    @staticmethod
    def _matched_keys(correct: dict[str, str], submitted: dict[str, str]) -> list[str]:
        """Keys the user answered correctly (case- and whitespace-insensitive)."""
        return [
            key
            for key, expected in correct.items()
            if submitted.get(str(key), "").strip().lower() == expected.strip().lower()
        ]

    @staticmethod
    def _mistake_budget_blown(ex, data: SubmitAttemptRequest) -> bool:
        # Only match-pairs carries a mistake budget; other types ignore it.
        limit = (ex.payload or {}).get("max_mistakes")
        return bool(limit) and (data.mistakes or 0) >= limit

    async def _feed_pairs(self, user_id: int, ex, correct: dict[str, str], submitted: dict[str, str]) -> None:
        """Review every word the user actually reached in a match-pairs round.

        Pairs that never appeared carry no signal, so they are left untouched
        rather than counted as failures.
        """
        for pair in (ex.payload or {}).get("pairs", []):
            word_uuid, pair_id = pair.get("word_uuid"), str(pair.get("id"))
            if not word_uuid or pair_id not in submitted:
                continue
            got = submitted[pair_id].strip().lower()
            expected = correct.get(pair_id, "").strip().lower()
            quality = _QUALITY_CORRECT if got == expected else _QUALITY_INCORRECT
            await self._feed_spaced_repetition(user_id, UUID(word_uuid), quality)
        # A round covers many words, so there is no single mastery level to report.
        return None

    async def _feed_spaced_repetition(self, user_id: int, word_uuid: UUID | None, quality: int) -> str | None:
        # Answering an exercise counts as a review of that word, if it's in the
        # user's vocabulary.
        if not word_uuid:
            return None
        uw = await self.user_words.get_by_user_word(user_id, word_uuid)
        if not uw:
            return None
        result = await SpacedRepetitionService(self.session).review(user_id, uw.uuid, quality)
        return result.mastery_level


async def get_exercise_pool_service(
    session: AsyncSession = Depends(get_session),
    generator: ExerciseGenerationService = Depends(get_exercise_generation_service),
) -> ExercisePoolService:
    return ExercisePoolService(session, generator)


async def translation_language_for(session: AsyncSession, user_id: int) -> str:
    """The language a user's words are translated into."""
    user = await UserRepository(session).get_by_id(user_id)
    return (user and user.native_language) or settings.exercises.EXERCISE_FALLBACK_TRANSLATION_LANGUAGE


async def translate_word_in_background(user_id: int, word_uuid: UUID) -> None:
    """Translate a freshly captured word for FastAPI BackgroundTasks.

    Doing it once per word at capture time means a match-pairs round can later
    be built entirely from cached translations, with no inference at all.
    """
    from app.database.postgres import async_session
    from app.services.ai.client import AIClient
    from app.services.vocabulary.translation_service import TranslationService

    try:
        async with async_session() as session:
            word = await WordRepository(session).get_one(uuid=word_uuid)
            if not word:
                return
            language = await translation_language_for(session, user_id)
            service = TranslationService(session, ExerciseGenerationService(AIClient()))
            translation = await service.translate_word(word, language)
            if translation:
                logger.info("Translated %r -> %r (%s)", word.lemma, translation, language)
    except Exception:  # noqa: BLE001 — background task must never crash the worker
        logger.exception("Background translation failed for word %s", word_uuid)


async def refill_pool_in_background(user_id: int) -> None:
    """Standalone pool refill for FastAPI BackgroundTasks.

    Runs after the response is sent, so it opens its own session and AI client
    and never propagates errors to the request.
    """
    from app.database.postgres import async_session
    from app.services.ai.client import AIClient

    try:
        async with async_session() as session:
            service = ExercisePoolService(session, ExerciseGenerationService(AIClient()))
            await service.replenish(user_id)
    except Exception:  # noqa: BLE001 — background task must never crash the worker
        logger.exception("Background pool refill failed for user %s", user_id)
