"""Request-scoped logging middleware.

Every request gets a **request ID**: a short random token that appears in every log line the
request produces and is returned in the ``X-Request-ID`` response header. When a user reports
"it failed at 3:02pm", the header value from their failed response finds every log line of
exactly that request — across API, and (because it is bound before the handler runs) anything
the handler logged. Without one, concurrent requests interleave their log lines into soup.
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger("app.request")

# Liveness probes fire every few seconds forever. Logging them would make the production log
# mostly heartbeat noise, and noise is what makes real signals get missed.
_UNLOGGED_PATHS = {"/health", "/health/ready"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Generated fresh, never taken from an inbound header: this ID is our correlation
        # token, and accepting a client-supplied one would let a caller pollute the logs
        # with someone else's ID (or with junk).
        request_id = uuid.uuid4().hex[:12]

        # contextvars, not a function argument: anything this request's handler logs — three
        # calls deep in a service — picks the ID up automatically via merge_contextvars.
        # clear() first because the worker process reuses tasks' contexts.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Unhandled exceptions still return a 500 through Starlette's error handling
            # (and reach Sentry); this line makes sure the request they belong to is
            # identifiable in the log even though no response line will be written.
            logger.exception(
                "request failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
            )
            raise

        if request.url.path not in _UNLOGGED_PATHS:
            logger.info(
                "request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
            )

        response.headers["X-Request-ID"] = request_id
        return response
