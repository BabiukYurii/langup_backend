# Google ID-token verification. Kept behind a small factory so tests can
# inject a fake verifier without hitting Google.
from collections.abc import Callable

from app.core import settings
from app.core.exc import UnauthorizedException

GoogleVerifier = Callable[[str], dict]


def verify_google_id_token(token: str) -> dict:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    audience = settings.auth.GOOGLE_CLIENT_ID or None
    try:
        return google_id_token.verify_oauth2_token(token, google_requests.Request(), audience)
    except Exception as exc:  # noqa: BLE001 - any failure means the token is untrusted
        raise UnauthorizedException("Invalid Google token") from exc


def get_google_verifier() -> GoogleVerifier:
    return verify_google_id_token
