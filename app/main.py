# FastAPI application factory: wires routers, middleware, exception handlers,
# logging, lifespan (event consumer + websocket manager startup).
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="LangUp")
    # include_router(app); add_middleware(app); add_exception_handlers(app)
    return app
