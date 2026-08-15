"""Rate-limit enforcement as a FastAPI dependency.

The algorithm lives in ``app/core/rate_limit.py`` and knows nothing about HTTP; this module
is the thin adapter that extracts a client identity from the request, looks up the limits in
settings, and turns a rejection into a ``429 Too Many Requests``.

Attached per-route via ``dependencies=[Depends(rate_limit("login"))]`` rather than as global
middleware, because the limits are not uniform: five login attempts and five job-list reads
are not the same kind of event. Only the endpoints where abuse is cheap for the attacker and
expensive for us — the unauthenticated credential endpoints — carry a limiter at all.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, status

from app.core.config import get_settings
from app.core.rate_limit import RateLimiter, RedisRateLimiter

RateLimitScope = Literal["login", "register", "refresh"]

_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Process-wide limiter singleton.

    A provider function rather than a module-level instance so tests can override it through
    ``app.dependency_overrides`` — the same seam every repository and service already uses.
    """
    global _limiter  # deliberate module singleton, same pattern as the db engine
    if _limiter is None:
        _limiter = RedisRateLimiter(str(get_settings().redis_url))
    return _limiter


RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


def _limits_for(scope: RateLimitScope) -> tuple[int, int]:
    """Resolve (limit, window seconds) from settings at request time.

    Read per-request rather than captured at import, so tests — and a future admin toggle —
    can change limits without rebuilding the app.
    """
    settings = get_settings()
    if scope == "login":
        return settings.rate_limit_login, settings.rate_limit_login_window_seconds
    if scope == "register":
        return settings.rate_limit_register, settings.rate_limit_register_window_seconds
    return settings.rate_limit_refresh, settings.rate_limit_refresh_window_seconds


def rate_limit(scope: RateLimitScope) -> Callable[..., Awaitable[None]]:
    """Build a dependency that enforces the named scope's limit per client IP.

    Keyed by IP because these endpoints are exactly the ones with no authenticated identity
    to key on — login *is* the act of establishing one. Uvicorn runs with
    ``--proxy-headers``, so behind Render's proxy ``request.client.host`` is the real client
    address taken from ``X-Forwarded-For``, not the proxy's own.
    """

    async def _enforce(request: Request, limiter: RateLimiterDep) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return

        limit, window_seconds = _limits_for(scope)
        client_ip = request.client.host if request.client else "unknown"
        decision = await limiter.hit(f"ratelimit:{scope}:{client_ip}", limit, window_seconds)

        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                # RFC 6585: Retry-After tells the client when a retry can succeed. Without
                # it, clients retry immediately and turn one rejection into a stampede.
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )

    return _enforce
