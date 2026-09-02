# FastAPI application factory: wires routers, middleware and exception handlers.
import hashlib
import re
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
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
    ServiceUnavailableException,
    UnauthorizedException,
    handlers,
)
from app.middlewares.security_headers import SecurityHeadersMiddleware
from app.routers import router

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# The Flutter web build, when one has been placed here. It is not in the repo:
# building it needs the Flutter SDK, which has no business in this image, so the
# artifact is produced elsewhere and bind-mounted (see docker-compose).
#
# Its presence is what selects the cabinet: with a build in place the Flutter
# app is served, without one the original HTML cabinet is. That makes the switch
# — and the way back — a matter of what is on disk, with no code change and no
# redeploy of the API.
_WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"


def _add_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ObjectNotFoundException, handlers.handle_object_not_found)
    app.add_exception_handler(ObjectAlreadyExistsException, handlers.handle_object_already_exists)
    app.add_exception_handler(BadRequestException, handlers.handle_bad_request)
    app.add_exception_handler(UnauthorizedException, handlers.handle_unauthorized)
    app.add_exception_handler(ForbiddenException, handlers.handle_forbidden)
    app.add_exception_handler(ServerErrorException, handlers.handle_server_error)
    app.add_exception_handler(RateLimitedException, handlers.handle_rate_limited)
    app.add_exception_handler(ServiceUnavailableException, handlers.handle_service_unavailable)
    app.add_exception_handler(AIProviderError, handlers.handle_ai_provider_error)
    app.add_exception_handler(AIResponseValidationError, handlers.handle_ai_response_validation)


_NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}
# Safe only because the URL carries a build stamp: a new build is a new path,
# so nothing cached under the old one can ever be served in its place.
_IMMUTABLE_ASSET = {"Cache-Control": "public, max-age=31536000, immutable"}
_SAFE_PAGE = re.compile(r"^[a-z0-9_-]+$")

# Where each page of the old HTML cabinet lives in the app now. Anything not
# listed goes to the root, which routes on to login or the dashboard.
_LEGACY_ROUTES = {
    "index": "/",
    "words": "/words",
    "practice": "/practice",
    "review": "/review",
    "dashboard": "/dashboard",
    "playlist": "/playlists",
}


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


def _build_stamp() -> str:
    """A short id that changes whenever the build does.

    Content, not timestamps: the build is copied onto the server with rsync,
    which preserves mtimes, so a file that did not change keeps its old one —
    and a file that did would otherwise have to be noticed by clock alone.
    """
    entry = _WEBAPP_DIR / "main.dart.js"
    if not entry.is_file():
        return "0"
    digest = hashlib.sha256()
    with entry.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()[:12]


def _register_flutter_app(app: FastAPI) -> None:
    """Serve the Flutter web build at /app, with every asset URL versioned.

    Flutter emits `main.dart.js` under a fixed name with no version in it, so a
    deploy changes what that URL means without changing the URL — exactly what
    a cache is entitled to ignore. Cloudflare makes that concrete: it rewrites
    our `no-cache` into its own four-hour browser TTL, so users would keep
    running yesterday's app for hours.

    So assets are served under /app/v/<stamp>/, and the stamp moves with the
    build. A deploy produces URLs nothing has ever seen, which no cache can
    answer stale — and precisely because of that, those URLs are then safe to
    mark immutable, so a returning user re-downloads nothing.

    Only index.html is uncached, and it is ~2 KB carrying the current stamp.

    An unknown stamp still serves the current files rather than 404-ing: a
    browser holding an older index must get a working app, not a blank page.
    """

    def index() -> HTMLResponse:
        html = (_WEBAPP_DIR / "index.html").read_text(encoding="utf-8")
        # Flutter resolves every asset against <base>, so redirecting that one
        # tag moves the whole app onto the versioned path.
        html = html.replace('<base href="/app/">', f'<base href="/app/v/{_build_stamp()}/">')
        return HTMLResponse(html, headers=_NO_CACHE)

    @app.get("/app", include_in_schema=False)
    @app.get("/app/", include_in_schema=False)
    async def flutter_index() -> HTMLResponse:
        return index()

    # The whole hostname belongs to LangUp — the landing page lives on the apex
    # domain — so the root has nothing else to be. It answered 404 before, which
    # is simply where people type first.
    @app.get("/", include_in_schema=False)
    async def flutter_root() -> RedirectResponse:
        return RedirectResponse("/app/")

    # The old cabinet was a page per URL; the app routes on the fragment, which
    # a server never sees. So a bookmark can only be sent to the right screen by
    # mapping it here — otherwise every saved link lands on a 404.
    @app.get("/app/{name}.html", include_in_schema=False)
    async def legacy_page(name: str) -> RedirectResponse:
        return RedirectResponse(f"/app/#{_LEGACY_ROUTES.get(name, '/')}")

    @app.get("/app/v/{stamp}/{path:path}", include_in_schema=False)
    async def flutter_asset(stamp: str, path: str) -> Response:
        target = (_WEBAPP_DIR / path).resolve()
        # Keep the traversal inside the build directory: `path` is user input.
        if not target.is_relative_to(_WEBAPP_DIR.resolve()) or not target.is_file():
            raise ObjectNotFoundException(path, "Asset")
        return FileResponse(target, headers=_IMMUTABLE_ASSET)


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

    # Serve the cabinet at /app (same origin as the API, so no CORS and no
    # second deployment). The Flutter build wins when it is present.
    if (_WEBAPP_DIR / "index.html").is_file():
        _register_flutter_app(app)
    elif _FRONTEND_DIR.is_dir():
        _register_cabinet(app)

    return app


# Module-level ASGI app for production servers (e.g. `uvicorn app.main:app`).
app = create_app()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.app.HOST, port=settings.app.PORT)
