from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exc.ai import AIProviderError, AIResponseValidationError
from app.core.exc.base import (
    BadRequestException,
    ForbiddenException,
    ObjectAlreadyExistsException,
    ObjectNotFoundException,
    RateLimitedException,
    ServerErrorException,
    ServiceUnavailableException,
    UnauthorizedException,
)


def _json(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": message})


async def handle_object_not_found(_: Request, exc: ObjectNotFoundException) -> JSONResponse:
    return _json(404, exc.message)


async def handle_object_already_exists(_: Request, exc: ObjectAlreadyExistsException) -> JSONResponse:
    return _json(409, exc.message)


async def handle_bad_request(_: Request, exc: BadRequestException) -> JSONResponse:
    return _json(400, exc.message)


async def handle_unauthorized(_: Request, exc: UnauthorizedException) -> JSONResponse:
    return _json(401, exc.message)


async def handle_forbidden(_: Request, exc: ForbiddenException) -> JSONResponse:
    return _json(403, exc.message)


async def handle_server_error(_: Request, exc: ServerErrorException) -> JSONResponse:
    return _json(500, exc.message)


async def handle_service_unavailable(_: Request, exc: ServiceUnavailableException) -> JSONResponse:
    return _json(503, exc.message)


async def handle_ai_provider_error(_: Request, exc: AIProviderError) -> JSONResponse:
    return _json(503, exc.message)


async def handle_ai_response_validation(_: Request, exc: AIResponseValidationError) -> JSONResponse:
    return _json(502, exc.message)


async def handle_rate_limited(_: Request, exc: RateLimitedException) -> JSONResponse:
    # Retry-After tells a well-behaved client exactly how long to back off.
    return JSONResponse(
        status_code=429,
        content={"detail": exc.message},
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )
