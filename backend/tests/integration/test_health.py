"""Health and readiness endpoints, exercised through the real ASGI stack."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


class TestLiveness:
    async def test_returns_ok(self, client: AsyncClient) -> None:
        response = await client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["service"] == "CareerGraph"
        assert body["version"] == "0.1.0"

    async def test_is_not_versioned(self, client: AsyncClient) -> None:
        # Health checks are infrastructure, not API surface. They must not move when the API
        # is versioned, or every platform probe breaks on the day v2 ships.
        assert (await client.get("/api/v1/health")).status_code == 404


class TestReadiness:
    async def test_reports_ready_when_dependencies_are_reachable(self, client: AsyncClient) -> None:
        response = await client.get("/health/ready")

        # 200 whether or not Redis is up: Redis is not critical, so its absence degrades the
        # service rather than making it unavailable.
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"ready", "degraded"}

        postgres = next(d for d in body["dependencies"] if d["name"] == "postgres")
        assert postgres["healthy"] is True
        assert postgres["critical"] is True

    async def test_reports_redis_separately_and_as_non_critical(self, client: AsyncClient) -> None:
        """A dead queue must be visible without taking the service out of rotation.

        Without this, a deployment missing REDIS_URL reports "ready" while every upload sits
        in `pending` forever — the exact failure ADR-0008 warns about.
        """
        body = (await client.get("/health/ready")).json()

        redis = next(d for d in body["dependencies"] if d["name"] == "redis")
        assert redis["critical"] is False
        # Degraded when Redis is down, ready when it is up — never silently "ready" either way.
        assert body["status"] == ("ready" if redis["healthy"] else "degraded")

    async def test_does_not_leak_connection_details(self, client: AsyncClient) -> None:
        # This endpoint is unauthenticated. A failure detail must never contain a host,
        # username, or password — so we assert the response body never carries credentials.
        body = (await client.get("/health/ready")).text
        assert "password" not in body.lower()
        assert "5432" not in body


class TestOpenApi:
    async def test_schema_is_served(self, client: AsyncClient) -> None:
        response = await client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "CareerGraph"
        assert "/health" in schema["paths"]

    async def test_swagger_ui_is_available_outside_production(self, client: AsyncClient) -> None:
        assert (await client.get("/docs")).status_code == 200
