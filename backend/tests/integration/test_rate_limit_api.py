"""Rate limiting through the real HTTP stack.

The unit tests prove the window algorithm; these prove the wiring — that the dependency is
actually attached to the routes, that a rejection surfaces as 429 with a Retry-After header,
and that the suite-wide kill switch (RATE_LIMIT_ENABLED=false in conftest) can be overridden.

The Redis-backed limiter is swapped for the in-memory implementation via
``dependency_overrides``: CI has Postgres but no Redis service, and what is under test here
is the HTTP behaviour, not the storage backend.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.rate_limit import get_rate_limiter
from app.core.config import get_settings
from app.core.rate_limit import InMemoryRateLimiter

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def rate_limited_app(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> Generator[FastAPI, None, None]:
    """Enable rate limiting with a tight login limit, backed by an in-memory limiter.

    ``get_settings`` is lru_cached, so changing the environment is not enough — the cache
    must be cleared both before the test (to pick the values up) and after (so no later test
    inherits them).
    """
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_LOGIN", "3")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_WINDOW_SECONDS", "60")
    get_settings.cache_clear()

    # One shared instance, captured in a closure. Overriding with the class itself would
    # construct a fresh limiter per request, and a counter that resets on every request
    # never rejects anything.
    limiter = InMemoryRateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    yield app

    get_settings.cache_clear()


async def _register(client: AsyncClient, email: str = "limited@example.com") -> None:
    response = await client.post(f"{AUTH}/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text


async def test_login_over_the_limit_returns_429_with_retry_after(
    rate_limited_app: FastAPI, client: AsyncClient
) -> None:
    await _register(client)

    for _ in range(3):
        response = await client.post(
            f"{AUTH}/login", json={"email": "limited@example.com", "password": "wrong-password!"}
        )
        assert response.status_code == 401

    # The fourth attempt is rejected before credentials are even checked — a correct
    # password makes no difference, which is the point: the limiter counts requests,
    # not failures, so it cannot be used to distinguish a right guess from a wrong one.
    response = await client.post(
        f"{AUTH}/login", json={"email": "limited@example.com", "password": PASSWORD}
    )
    assert response.status_code == 429
    assert "retry-after" in {k.lower() for k in response.headers}
    assert int(response.headers["Retry-After"]) >= 1


async def test_other_scopes_are_not_affected_by_an_exhausted_login_limit(
    rate_limited_app: FastAPI, client: AsyncClient
) -> None:
    await _register(client)
    for _ in range(4):
        await client.post(
            f"{AUTH}/login", json={"email": "limited@example.com", "password": "wrong-password!"}
        )

    # Registration has its own counter and its own (default, generous) limit.
    response = await client.post(
        f"{AUTH}/register", json={"email": "someone-else@example.com", "password": PASSWORD}
    )
    assert response.status_code == 201


async def test_limits_do_not_apply_when_disabled(client: AsyncClient) -> None:
    """The suite-wide default: RATE_LIMIT_ENABLED=false means unlimited attempts.

    Guards the conftest kill switch itself — if this breaks, every other integration test
    that logs in repeatedly starts failing with mysterious 429s.
    """
    await _register(client)
    for _ in range(15):
        response = await client.post(
            f"{AUTH}/login", json={"email": "limited@example.com", "password": "wrong-password!"}
        )
        assert response.status_code == 401
