# FastAPI application factory: wires routers, middleware and exception handlers.
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import settings
from app.core.exc import (
    BadRequestException,
    ForbiddenException,
    ObjectAlreadyExistsException,
    ObjectNotFoundException,
    ServerErrorException,
    UnauthorizedException,
    handlers,
)
from app.routers import router


def _add_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ObjectNotFoundException, handlers.handle_object_not_found)
    app.add_exception_handler(ObjectAlreadyExistsException, handlers.handle_object_already_exists)
    app.add_exception_handler(BadRequestException, handlers.handle_bad_request)
    app.add_exception_handler(UnauthorizedException, handlers.handle_unauthorized)
    app.add_exception_handler(ForbiddenException, handlers.handle_forbidden)
    app.add_exception_handler(ServerErrorException, handlers.handle_server_error)


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app.APP_NAME)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    _add_handlers(app)
    return app


if __name__ == "__main__":
    uvicorn.run("app.main:create_app", host=settings.app.HOST, port=settings.app.PORT, factory=True)
