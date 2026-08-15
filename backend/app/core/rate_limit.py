"""Fixed-window rate limiting.

**Rate limiting** caps how many times a client may call an endpoint within a time window.
Without it, the cost of guessing a password is however fast an attacker can send requests;
with it, the cost is however fast the *server allows* — think of a bank cashier who will
serve you all day, but only lets any one customer reach the counter ten times an hour.

The algorithm here is a **fixed window**: a counter per (scope, client) that resets every
`window_seconds`. It is deliberately the simplest correct option — one counter, two Redis
commands — at the cost of a known edge: a client can send `limit` requests at the end of one
window and `limit` more at the start of the next, briefly doubling the rate. For an
authentication brute-force control that is irrelevant (20 guesses instead of 10 does not
crack an Argon2-hashed passphrase); for strict API metering you would use a sliding window.
See ADR-0011 for why this is hand-rolled rather than a library.

Two implementations of the same protocol:

* ``RedisRateLimiter`` — the real one. State lives in Redis, so it survives process restarts
  and is shared across instances if the API ever scales horizontally.
* ``InMemoryRateLimiter`` — the same algorithm in a dict, for tests and for running the API
  with no Redis at all. Per-process, so it must never be used in production behind more than
  one worker.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

# A limiter that hangs is worse than one that fails: every login would wait on it. Redis is
# on the same network as the API; if it cannot answer in a second, treat it as down.
_REDIS_TIMEOUT_SECONDS = 1.0


@dataclass(frozen=True)
class RateLimitDecision:
    """The answer to "may this request proceed?".

    ``retry_after_seconds`` is only meaningful when ``allowed`` is False; it becomes the
    HTTP ``Retry-After`` header, which tells a well-behaved client exactly when trying
    again will succeed instead of leaving it to guess.
    """

    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter(Protocol):
    """What the HTTP layer needs from a limiter — one method, no Redis visible.

    A Protocol for the same reason the repositories use them: the dependency can be swapped
    for an in-memory fake in tests without patching module globals.
    """

    async def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        """Record one request against ``key`` and decide whether it may proceed."""
        ...


class InMemoryRateLimiter:
    """Fixed window over a plain dict.

    The clock is injectable so unit tests can advance time instantly instead of sleeping
    through a real window.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        # key -> (window start, count within that window)
        self._windows: dict[str, tuple[float, int]] = {}

    async def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        now = self._clock()
        window_start, count = self._windows.get(key, (now, 0))

        if now - window_start >= window_seconds:
            # The previous window has fully elapsed; start a fresh one.
            window_start, count = now, 0

        count += 1
        self._windows[key] = (window_start, count)

        if count > limit:
            remaining = window_seconds - (now - window_start)
            # Round up: telling a client "retry after 0" when 0.4s remain invites an
            # immediate retry that will also be rejected.
            return RateLimitDecision(allowed=False, retry_after_seconds=max(1, int(remaining) + 1))
        return RateLimitDecision(allowed=True)


class RedisRateLimiter:
    """Fixed window in Redis: ``INCR`` the counter, ``EXPIRE`` it on first hit.

    **Fails open.** If Redis is unreachable the request is allowed and the failure is left
    to the readiness probe to surface. This mirrors the decision already made in
    ``/health/ready``: Redis down degrades the service, it does not take it down. The
    alternative — failing closed — turns a Redis blip into "nobody can log in", which is a
    denial of service we would be inflicting on ourselves.
    """

    def __init__(self, redis_url: str, client: Any = None) -> None:
        self._redis_url = redis_url
        # `Any` rather than `Redis`, for two reasons: redis-py types every command as
        # `ResponseT` (a union with Awaitable[Any]) so precise typing buys nothing, and the
        # unit tests inject a dict-backed fake through this parameter. Created lazily so
        # importing this module never pays for a connection.
        self._client: Any = client

    def _get_client(self) -> Any:
        if self._client is None:
            # Imported here, not at module scope, for the same reason as the health probe:
            # the API process should not require a redis client just to import its modules.
            from redis.asyncio import Redis

            self._client = Redis.from_url(self._redis_url)
        return self._client

    async def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        try:
            client = self._get_client()
            async with asyncio.timeout(_REDIS_TIMEOUT_SECONDS):
                count = int(await client.incr(key))
                if count == 1:
                    await client.expire(key, window_seconds)

                if count <= limit:
                    return RateLimitDecision(allowed=True)

                ttl = int(await client.ttl(key))
                if ttl < 0:
                    # The key has no expiry — the process died between INCR and EXPIRE on
                    # the first hit. Without this repair the counter would never reset and
                    # the client would be locked out permanently.
                    await client.expire(key, window_seconds)
                    ttl = window_seconds
                return RateLimitDecision(allowed=False, retry_after_seconds=max(1, ttl))
        except Exception:  # any Redis failure means "limiter unavailable", never "reject"
            return RateLimitDecision(allowed=True)
