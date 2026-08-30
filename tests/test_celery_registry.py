"""Every task module must be in the Celery app's include list.

A task the worker does not import is not registered, so the web process
enqueues it happily and the worker rejects the message as unknown — the job
silently never runs. That is exactly how the audio warm-up shipped broken, so
it is checked rather than remembered.
"""

import pkgutil

import app.celery.tasks as tasks_pkg
from app.celery.config import celery_app


def test_every_task_module_is_included():
    on_disk = {f"app.celery.tasks.{m.name}" for m in pkgutil.iter_modules(tasks_pkg.__path__)}
    included = set(celery_app.conf.include or [])
    assert on_disk - included == set(), f"not registered with the worker: {on_disk - included}"


def test_the_audio_warmup_task_is_registered():
    __import__("app.celery.tasks.audio_tasks")
    assert "audio.warm_word" in celery_app.tasks
