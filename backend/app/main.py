"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
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

    configure_logging(log_level=settings.log_level, environment=settings.environment)

    # Sentry is an error-tracking service: unhandled exceptions are captured with their full
    # stack trace, request context, and frequency, and grouped into issues — so "something
    # broke in production" arrives as an alert with a traceback instead of a user complaint.
    # Logs tell you what happened in order; Sentry tells you what is *broken* right now.
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            # Resumes and emails pass through this API. Sentry must see stack traces, never
            # request bodies or user PII — a debugging tool must not become a data leak.
            send_default_pii=False,
        )

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

    # Added after CORS, which makes it the *outer* layer (Starlette middleware is an onion:
    # last added runs first). The request ID must exist before anything else can log.
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
