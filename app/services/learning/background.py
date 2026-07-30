"""Choosing how background work runs.

With a worker up, jobs go to Celery: they survive a restart, retry on failure,
and queue behind one another instead of all hitting the single-CPU model at
once. Without one, they fall back to FastAPI BackgroundTasks — good enough for
a single small instance, and what tests use.
"""

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import BackgroundTasks

from app.core import settings
from app.enums.learning import ExerciseType

if TYPE_CHECKING:
    from app.schemas.exercise import RefillStatusOut

logger = logging.getLogger(__name__)


def _enqueue(task, *args) -> str | None:
    """Hand a job to Celery; None means the broker would not take it."""
    if not settings.celery.CELERY_ENABLED:
        return None
    try:
        return task.delay(*args).id
    except Exception:  # noqa: BLE001 — a broker outage must not fail the request
        logger.exception("Could not enqueue %s, falling back to in-process", task.name)
        return None


def schedule_translation(background: BackgroundTasks, user_id: int, word_uuid: UUID) -> None:
    from app.celery.tasks.ai_tasks import translate_word
    from app.services.learning.exercise_service import translate_word_in_background

    if _enqueue(translate_word, user_id, str(word_uuid)) is None:
        background.add_task(translate_word_in_background, user_id, word_uuid)


def schedule_refill(background: BackgroundTasks, user_id: int) -> None:
    from app.celery.tasks.ai_tasks import refill_pool
    from app.services.learning.exercise_service import refill_pool_in_background

    if _enqueue(refill_pool, user_id) is None:
        background.add_task(refill_pool_in_background, user_id)


def schedule_verification_email(
    background: BackgroundTasks, to: str, subject: str, html: str, text: str | None = None
) -> None:
    """Send a transactional email off the request path (Celery, else in-process)."""
    from app.celery.tasks.email_tasks import send_email_task
    from app.services.notifications.mailer import send_email

    if _enqueue(send_email_task, to, subject, html, text) is None:
        background.add_task(send_email, to, subject, html, text)


def enqueue_refill(user_id: int, exercise_type: ExerciseType | None) -> str | None:
    """Queue an on-demand refill; None means the caller should do it itself."""
    from app.celery.tasks.ai_tasks import refill_pool

    return _enqueue(refill_pool, user_id, exercise_type.value if exercise_type else None)


# Celery has many states; the UI only needs to know whether to keep waiting.
_STATUS = {
    "PENDING": "pending",
    "RECEIVED": "pending",
    "RETRY": "pending",
    "STARTED": "running",
    "SUCCESS": "done",
}


def refill_task_status(task_id: str) -> "RefillStatusOut":
    from app.celery.config import celery_app
    from app.schemas.exercise import RefillStatusOut

    result = celery_app.AsyncResult(task_id)
    status = _STATUS.get(result.state, "failed")
    # result.result holds the exception on failure, so only read it when done.
    created = result.result if status == "done" and isinstance(result.result, int) else None
    return RefillStatusOut(status=status, created=created)
