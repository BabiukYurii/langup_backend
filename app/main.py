# FastAPI application factory: wires routers, middleware and exception handlers.
import re
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app.core import settings
from app.core.exc import (
    AIProviderError,
    AIResponseValidationError,
    BadRequestException,
    ForbiddenException,
    ObjectAlreadyExistsException,
    ObjectNotFoundException,
    RateLimitedException,
    ServerErrorException,
    UnauthorizedException,
    handlers,
)
from app.middlewares.security_headers import SecurityHeadersMiddleware
from app.routers import router

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def _add_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ObjectNotFoundException, handlers.handle_object_not_found)
    app.add_exception_handler(ObjectAlreadyExistsException, handlers.handle_object_already_exists)
    app.add_exception_handler(BadRequestException, handlers.handle_bad_request)
    app.add_exception_handler(UnauthorizedException, handlers.handle_unauthorized)
    app.add_exception_handler(ForbiddenException, handlers.handle_forbidden)
    app.add_exception_handler(ServerErrorException, handlers.handle_server_error)
    app.add_exception_handler(RateLimitedException, handlers.handle_rate_limited)
    app.add_exception_handler(AIProviderError, handlers.handle_ai_provider_error)
    app.add_exception_handler(AIResponseValidationError, handlers.handle_ai_response_validation)


_NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}
_SAFE_PAGE = re.compile(r"^[a-z0-9_-]+$")


class _CabinetFiles(StaticFiles):
    """Cabinet assets, asking the CDN in front of us not to hold on to them."""

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers.update(_NO_CACHE)
        return response


def _asset_version() -> str:
    """Stamp for cabinet asset URLs, derived from when they last changed.

    Cloudflare rewrites our `no-cache` into its own four-hour browser TTL, so a
    deploy would otherwise leave browsers running yesterday's scripts. A version
    that moves with the files sidesteps caching entirely: new deploy, new URL.
    """
    newest = max(
        (path.stat().st_mtime for pattern in ("*.js", "*.css") for path in _FRONTEND_DIR.glob(pattern)),
        default=0.0,
    )
    return f"{int(newest):x}"


def _register_cabinet(app: FastAPI) -> None:
    """Serve the cabinet: HTML rendered with a version stamp, assets as files."""
    version = _asset_version()

    def render(name: str) -> HTMLResponse:
        path = _FRONTEND_DIR / name
        if not _SAFE_PAGE.match(path.stem) or not path.is_file():
            raise ObjectNotFoundException(name, "Page")
        html = path.read_text(encoding="utf-8").replace("?v=dev", f"?v={version}")
        return HTMLResponse(html, headers=_NO_CACHE)

    @app.get("/app", include_in_schema=False)
    @app.get("/app/", include_in_schema=False)
    async def cabinet_index() -> HTMLResponse:
        return render("index.html")

    @app.get("/app/{name}.html", include_in_schema=False)
    async def cabinet_page(name: str) -> HTMLResponse:
        return render(f"{name}.html")

    app.mount("/app", _CabinetFiles(directory=_FRONTEND_DIR, html=True), name="frontend")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app.APP_NAME)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.ALLOWED_ORIGINS,
        # Auth is a Bearer token in the Authorization header, not cookies, so
        # credentialed CORS isn't needed (and pairs badly with a wildcard origin).
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    _add_handlers(app)

    # Serve the small profile frontend at /app (same origin as the API).
    if _FRONTEND_DIR.is_dir():
        _register_cabinet(app)

    return app


# Module-level ASGI app for production servers (e.g. `uvicorn app.main:app`).
app = create_app()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.app.HOST, port=settings.app.PORT)
