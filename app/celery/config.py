# Celery application: Redis broker/backend, one queue, AI tasks autodiscovered.
from celery import Celery

from app.core import settings

celery_app = Celery(
    "langup",
    broker=settings.redis.url,
    backend=settings.redis.url,
    include=[
        "app.celery.tasks.ai_tasks",
        "app.celery.tasks.audio_tasks",
        "app.celery.tasks.dictionary_tasks",
        "app.celery.tasks.email_tasks",
        "app.celery.tasks.playlist_tasks",
        "app.celery.tasks.warm_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # The UI polls a refill task, so it needs to see "started", not just
    # "pending", while the model is busy.
    task_track_started=True,
    task_time_limit=settings.celery.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=settings.celery.CELERY_TASK_SOFT_TIME_LIMIT,
    result_expires=settings.celery.CELERY_RESULT_EXPIRES_SECONDS,
    # Ollama runs one inference at a time on this CPU: letting the worker take
    # several jobs at once would only make them fight over the same cores.
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    # Warming rides in its own queue, served by its own worker. Without this it
    # would sit in the single default queue and a learner's refill would wait
    # behind a song nobody asked for yet. The queues do not solve contention on
    # the model itself — see services/learning/model_busy — they solve
    # contention on the worker slot, which is a different problem with the same
    # symptom.
    task_routes={"warm.*": {"queue": "warm"}},
)

# The first periodic work in the project: beat had been running with an empty
# schedule. One song per tick, deliberately unhurried — the model this competes
# for is the same one learners are waiting on.
celery_app.conf.beat_schedule = {
    "warm-one-playlist-song": {
        "task": "warm.tick",
        "schedule": float(settings.warm.WARM_TICK_SECONDS),
        # A tick that arrives while the last one is still running is pointless:
        # drop it rather than pile up a backlog of songs to warm.
        "options": {"expires": float(settings.warm.WARM_TICK_SECONDS)},
    }
}
