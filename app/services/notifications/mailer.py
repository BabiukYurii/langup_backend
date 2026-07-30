"""Outgoing email.

One entry point, `send_email`, used by every notification (currently just
account verification). When SMTP is not configured — dev, CI, tests — it logs
the message instead of sending, so the whole flow works without a provider and
without leaking mail in tests. aiosmtplib is imported lazily inside the send
path so those environments never need the package installed.
"""

import logging
from email.message import EmailMessage

from app.core import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, html: str, text: str | None = None) -> bool:
    """Send one email. Returns True if it went out over SMTP, False if it was
    only logged (SMTP disabled). Never raises for a delivery problem — callers
    run this in the background and must not fail the user's request over it."""
    if not settings.email.enabled:
        logger.info("Email (SMTP disabled) to=%s subject=%r\n%s", to, subject, text or html)
        return False

    message = EmailMessage()
    message["From"] = f"{settings.email.EMAIL_FROM_NAME} <{settings.email.EMAIL_FROM}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text or "Please view this message in an HTML-capable client.")
    message.add_alternative(html, subtype="html")

    try:
        import aiosmtplib

        await aiosmtplib.send(
            message,
            hostname=settings.email.SMTP_HOST,
            port=settings.email.SMTP_PORT,
            username=settings.email.SMTP_USER or None,
            password=settings.email.SMTP_PASSWORD or None,
            start_tls=settings.email.SMTP_STARTTLS,
        )
        return True
    except Exception:  # noqa: BLE001 — a mail outage must not break the caller
        logger.exception("Failed to send email to=%s subject=%r", to, subject)
        return False
