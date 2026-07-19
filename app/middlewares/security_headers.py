"""Baseline security response headers.

The cabinet is a tiny same-origin app served from /app, so a broad CSP would
mostly get in the way; the headers here are the cheap, high-value ones that
apply everywhere and cannot break the API.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_HEADERS = {
    # Never let a browser second-guess a declared content type.
    "X-Content-Type-Options": "nosniff",
    # The app is never meant to be framed — blunts clickjacking.
    "X-Frame-Options": "DENY",
    # Don't leak the full URL (which can carry ids) to other origins.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # We don't use these device APIs; deny them outright.
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    # Everything is HTTPS behind Cloudflare — pin browsers to it. Safe because
    # we never serve the app over plain HTTP.
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for name, value in _HEADERS.items():
            response.headers.setdefault(name, value)
        return response
