"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.errors import register_exception_handlers
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.db.session import engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown hooks.

    Disposing the engine on shutdown closes pooled connections cleanly. Without it, a rolling
    deploy leaves connections open until Postgres times them out, and on a free tier with a
    low connection cap that is enough to make the new instance fail to start.
    """
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """Build the application.

    A factory rather than a module-level ``app = FastAPI()`` so tests can construct an
    independent instance with different settings instead of mutating a shared global.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.project_name,
        description=(
            "Skill-gap analysis: resume parsing, semantic job matching, and graph-based "
            "learning paths."
        ),
        version="0.1.0",
        docs_url=settings.docs_url,
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
        lifespan=lifespan,
    )

    # CORS is an allowlist, never "*". The frontend runs on a different origin from the API,
    # so the browser will refuse cross-origin requests unless the API names that origin
    # explicitly. Allowing "*" would let any website on the internet call this API using a
    # logged-in visitor's browser.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
