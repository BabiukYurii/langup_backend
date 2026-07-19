"""Choosing between Celery and in-process background work.

The switch matters: with a worker the job survives a restart and retries, and
without one the request must still do the work rather than silently drop it.
"""

from uuid import uuid4

import pytest
from fastapi import BackgroundTasks

from app.core import settings
from app.services.learning import background


class FakeTask:
    """Stands in for a Celery task, optionally with an unreachable broker."""

    name = "ai.fake"

    def __init__(self, broker_down: bool = False) -> None:
        self.broker_down = broker_down
        self.calls: list[tuple] = []

    def delay(self, *args):
        self.calls.append(args)
        if self.broker_down:
            raise ConnectionError("broker unreachable")
        return type("AsyncResult", (), {"id": "task-123"})()


@pytest.fixture
def celery_on():
    original = settings.celery.CELERY_ENABLED
    settings.celery.CELERY_ENABLED = True
    yield
    settings.celery.CELERY_ENABLED = original


def test_tasks_are_bound_to_our_broker_not_celery_default():
    """Importing a task the way the web process does must reach OUR broker.

    With @shared_task the binding follows "the current app", and the web
    process never loads the worker's entry point — so tasks silently pointed at
    Celery's default amqp broker and every enqueue died with a refused
    connection while the worker itself looked perfectly healthy.
    """
    from app.celery.tasks.ai_tasks import refill_pool, translate_word

    for task in (refill_pool, translate_word):
        assert task.app.conf.broker_url == settings.redis.url
        assert "amqp" not in task.app.conf.broker_url


def test_nothing_is_enqueued_while_celery_is_off():
    task = FakeTask()
    assert background._enqueue(task, 1) is None
    assert task.calls == []


def test_job_goes_to_celery_when_enabled(celery_on):
    task = FakeTask()
    assert background._enqueue(task, 1, "x") == "task-123"
    assert task.calls == [(1, "x")]


def test_broker_outage_falls_back_instead_of_failing(celery_on):
    # a Redis hiccup must not turn into a failed capture
    assert background._enqueue(FakeTask(broker_down=True), 1) is None


def test_capture_work_runs_in_process_without_a_worker():
    tasks = BackgroundTasks()
    background.schedule_translation(tasks, user_id=1, word_uuid=uuid4())
    background.schedule_refill(tasks, user_id=1)

    assert len(tasks.tasks) == 2  # both scheduled locally


def test_capture_work_is_queued_when_a_worker_is_up(celery_on, monkeypatch):
    monkeypatch.setattr(background, "_enqueue", lambda *a: "task-123")
    tasks = BackgroundTasks()

    background.schedule_translation(tasks, user_id=1, word_uuid=uuid4())
    background.schedule_refill(tasks, user_id=1)

    assert tasks.tasks == []  # nothing left for the web process to do
