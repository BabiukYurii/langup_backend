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
from app.enums.learning import AttemptResult, ExerciseStatus, ExerciseType
from app.models import UserWord
from app.repositories.exercise import ExerciseRepository
from app.repositories.exercise_attempt import ExerciseAttemptRepository
from app.repositories.user_word import UserWordRepository
from app.schemas.ai import FillInBlankParams, WordExerciseParams
from app.schemas.exercise import AttemptResultOut, ExerciseOut, SubmitAttemptRequest
from app.services.ai.exercise_generation import ExerciseGenerationService, get_exercise_generation_service
from app.services.learning.spaced_repetition import SpacedRepetitionService

logger = logging.getLogger(__name__)

# Recall quality fed into SM-2 when an exercise is answered.
_QUALITY_CORRECT = 5
_QUALITY_INCORRECT = 2

# Exercise types the pool rotates through when replenishing.
_TYPE_CYCLE = [ExerciseType.FILL_IN_BLANKS, ExerciseType.MULTIPLE_CHOICE, ExerciseType.FLASHCARD]

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
        self.generator = generator

    async def get_next(self, user_id: int) -> ExerciseOut:
        """Hand out the next pending exercise (re-serving an unanswered one first)."""
        ex = await self.exercises.next_pending(user_id)
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
        is_correct = self._grade(correct, data.answers)
        result = AttemptResult.CORRECT if is_correct else AttemptResult.INCORRECT
        quality = _QUALITY_CORRECT if is_correct else _QUALITY_INCORRECT

        await self.attempts.create_one(
            {
                "user_id": user_id,
                "exercise_uuid": ex.uuid,
                "submitted_answer": data.answers,
                "result": result.value,
                "quality": quality,
                "response_time_ms": data.response_time_ms,
            }
        )
        await self.exercises.update_one(ex, {"status": ExerciseStatus.COMPLETED.value})

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

        candidates = await self.user_words.list_due(user_id, _utcnow(), limit=need)
        if not candidates:
            candidates, _ = await self.user_words.list_for_user(user_id, page=1, limit=need)

        # Rotate exercise types; offset by the user's total so the same word
        # gets different types across refills.
        _, total_ever = await self.exercises.get_many(user_id=user_id, limit=1)

        created = 0
        for i, uw in enumerate(candidates):
            ex_type = _TYPE_CYCLE[(total_ever + i) % len(_TYPE_CYCLE)]
            try:
                await self._generate_and_store(user_id, uw, ex_type)
            except (AIProviderError, AIResponseValidationError) as e:
                logger.warning("Skipping %s exercise for %r: %s: %s", ex_type.value, uw.word.lemma, type(e).__name__, e)
                continue
            created += 1
        return created

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
    def _grade(correct: dict[str, str], submitted: dict[str, str]) -> bool:
        if not correct:
            return False
        for idx, expected in correct.items():
            given = submitted.get(str(idx), "")
            if given.strip().lower() != expected.strip().lower():
                return False
        return True

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
