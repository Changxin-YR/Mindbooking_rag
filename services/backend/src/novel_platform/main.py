from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from novel_platform.core.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from novel_platform.core.middleware import RequestContextMiddleware
from novel_platform.core.settings import Settings
from novel_platform.interfaces.http.health import build_health_router


def create_app() -> FastAPI:
    settings = Settings.from_env()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(build_health_router("root"))
    app.include_router(build_health_router("reader"), prefix="/api/v1")
    app.include_router(build_health_router("writer"), prefix="/writer/api/v1")
    app.include_router(build_health_router("admin"), prefix="/admin/api/v1")
    return app


app = create_app()
