from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.config import Settings
from backend.app.db import create_session_factory
from backend.app.errors import AppError, ServiceFailure, app_error_handler
from backend.app.limits import Limiter
from backend.app.request_limits import RequestSizeLimit
from backend.app.routers.auth import router as auth_router
from backend.app.routers.internal import router as internal_router
from backend.app.routers.items import router as items_router
from backend.app.routers.matches import router as matches_router
from backend.app.routers.metadata import router as metadata_router
from backend.app.storage import LocalStorage, build_storage


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine, factory = create_session_factory(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(title="FinDIU", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = factory
    app.state.storage = build_storage(settings)
    app.state.limiter = Limiter()
    app.include_router(auth_router)
    app.include_router(items_router)
    app.include_router(matches_router)
    app.include_router(metadata_router)
    app.include_router(internal_router)
    app.add_middleware(RequestSizeLimit)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_exception_handler(AppError, app_error_handler)

    @app.exception_handler(ServiceFailure)
    async def service_error(request: Request, error: ServiceFailure):
        return JSONResponse(
            status_code=503,
            content={
                "error": {"code": error.code, "message": "A service is temporarily unavailable."}
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "database_unavailable",
                    "message": "Database is temporarily unavailable.",
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # Pydantic's raw errors include original inputs, potentially passwords/private data.
        fields = [
            {"field": ".".join(map(str, e["loc"])), "code": e["type"]} for e in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Check the highlighted fields.",
                    "fields": fields,
                }
            },
        )

    @app.get("/health", tags=["operations"])
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/media/{key:path}", tags=["media"])
    def media(key: str, expires: int, signature: str):
        if not isinstance(app.state.storage, LocalStorage):
            raise AppError(404, "not_found", "Image not found.")
        path = app.state.storage.read(key, expires, signature)
        return FileResponse(
            path,
            media_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/ready", tags=["operations"])
    def readiness():
        try:
            with factory() as session:
                session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            raise AppError(
                503, "database_unavailable", "Database is temporarily unavailable."
            ) from None
        return {"status": "ready"}

    return app
