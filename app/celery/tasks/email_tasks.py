"""Email delivery jobs.

Sending goes through a worker when one is up so a slow SMTP handshake never
holds a web request. Without a worker the caller falls back to FastAPI
BackgroundTasks (see services/learning/background.py). Like the other tasks,
each run gets its own event loop.
"""

import asyncio
import logging

from app.celery.config import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="email.send")
def send_email_task(to: str, subject: str, html: str, text: str | None = None) -> bool:
    """Deliver one email (or log it when SMTP is disabled)."""
    from app.services.notifications.mailer import send_email

    sent = asyncio.run(send_email(to, subject, html, text))
    logger.info("email.send to=%s sent=%s", to, sent)
    return sent
