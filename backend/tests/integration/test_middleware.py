"""Request-context middleware, exercised through the real app."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_response_carries_a_request_id(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    request_id = response.headers.get("x-request-id")
    assert request_id is not None
    assert len(request_id) == 12


async def test_request_ids_are_unique_per_request(client: AsyncClient) -> None:
    first = await client.get("/health")
    second = await client.get("/health")
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


async def test_client_supplied_request_id_is_not_trusted(client: AsyncClient) -> None:
    """The ID is our correlation token; an inbound header must not overwrite it."""
    response = await client.get("/health", headers={"X-Request-ID": "attacker-chosen-value"})
    assert response.headers["x-request-id"] != "attacker-chosen-value"


async def test_errors_still_carry_a_request_id(client: AsyncClient) -> None:
    """The header matters most on failures — it is how a user report finds the log lines."""
    response = await client.get("/api/v1/resumes")  # no auth token → 401
    assert response.status_code == 401
    assert "x-request-id" in response.headers
