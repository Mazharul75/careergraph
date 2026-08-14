"""End-to-end authentication through the real HTTP stack and a real database.

The unit tests prove the rules. These prove the wiring: routing, Pydantic validation, the
dependency graph, exception translation to status codes, and the actual SQL.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
AUTH = "/api/v1/auth"


async def register(client: AsyncClient, email: str = "ada@example.com", **kwargs: object) -> dict:
    payload = {"email": email, "password": PASSWORD, "full_name": "Ada Lovelace", **kwargs}
    response = await client.post(f"{AUTH}/register", json=payload)
    assert response.status_code == 201, response.text
    body: dict = response.json()
    return body


async def login(client: AsyncClient, email: str = "ada@example.com") -> dict:
    response = await client.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    body: dict = response.json()
    return body


class TestRegistration:
    async def test_creates_an_account(self, client: AsyncClient) -> None:
        body = await register(client)

        assert body["email"] == "ada@example.com"
        assert body["role"] == "job_seeker"
        assert body["is_active"] is True

    async def test_response_never_contains_the_password_hash(self, client: AsyncClient) -> None:
        # The response schema has no such field, so this asserts the schema boundary holds.
        response = await client.post(
            f"{AUTH}/register",
            json={"email": "leak@example.com", "password": PASSWORD},
        )
        assert "password" not in response.text.lower()

    async def test_email_is_normalised(self, client: AsyncClient) -> None:
        body = await register(client, email="ADA@Example.COM")
        assert body["email"] == "ada@example.com"

    async def test_duplicate_email_returns_409(self, client: AsyncClient) -> None:
        await register(client)
        response = await client.post(
            f"{AUTH}/register",
            json={"email": "ADA@EXAMPLE.COM", "password": PASSWORD},
        )
        assert response.status_code == 409

    @pytest.mark.parametrize(
        "payload",
        [
            {"email": "not-an-email", "password": PASSWORD},
            {"email": "a@example.com", "password": "short"},
            {"email": "a@example.com"},
            {"password": PASSWORD},
        ],
    )
    async def test_invalid_input_returns_422(self, client: AsyncClient, payload: dict) -> None:
        # Pydantic rejects these at the boundary; no handler code runs.
        assert (await client.post(f"{AUTH}/register", json=payload)).status_code == 422

    async def test_can_register_a_recruiter(self, client: AsyncClient) -> None:
        body = await register(client, email="r@example.com", role="recruiter")
        assert body["role"] == "recruiter"

    async def test_cannot_invent_a_role(self, client: AsyncClient) -> None:
        # Privilege escalation via a request body must be impossible.
        response = await client.post(
            f"{AUTH}/register",
            json={"email": "x@example.com", "password": PASSWORD, "role": "admin"},
        )
        assert response.status_code == 422


class TestLogin:
    async def test_returns_a_token_pair(self, client: AsyncClient) -> None:
        await register(client)
        body = await login(client)

        assert body["access_token"]
        assert body["refresh_token"]
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900

    async def test_wrong_password_returns_401(self, client: AsyncClient) -> None:
        await register(client)
        response = await client.post(
            f"{AUTH}/login",
            json={"email": "ada@example.com", "password": "wrong-password-entirely"},
        )
        assert response.status_code == 401

    async def test_unknown_account_is_indistinguishable_from_a_wrong_password(
        self, client: AsyncClient
    ) -> None:
        await register(client)

        wrong_password = await client.post(
            f"{AUTH}/login",
            json={"email": "ada@example.com", "password": "wrong-password-entirely"},
        )
        no_such_user = await client.post(
            f"{AUTH}/login",
            json={"email": "nobody@example.com", "password": PASSWORD},
        )

        # Identical status and body — the API reveals nothing about which addresses exist.
        assert wrong_password.status_code == no_such_user.status_code == 401
        assert wrong_password.json() == no_such_user.json()


class TestProtectedRoute:
    async def test_access_token_grants_access(self, client: AsyncClient) -> None:
        await register(client)
        tokens = await login(client)

        response = await client.get(
            f"{AUTH}/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert response.status_code == 200
        assert response.json()["email"] == "ada@example.com"

    async def test_missing_header_returns_401_with_challenge(self, client: AsyncClient) -> None:
        response = await client.get(f"{AUTH}/me")
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"

    @pytest.mark.parametrize(
        "header",
        ["Bearer not-a-real-token", "Bearer ", "Basic dXNlcjpwYXNz", "garbage"],
    )
    async def test_bad_credentials_return_401(self, client: AsyncClient, header: str) -> None:
        response = await client.get(f"{AUTH}/me", headers={"Authorization": header})
        assert response.status_code == 401


class TestRefreshRotation:
    async def test_refresh_returns_a_new_pair(self, client: AsyncClient) -> None:
        await register(client)
        first = await login(client)

        response = await client.post(
            f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]}
        )
        assert response.status_code == 200
        second = response.json()
        assert second["refresh_token"] != first["refresh_token"]

    async def test_new_access_token_works(self, client: AsyncClient) -> None:
        await register(client)
        first = await login(client)
        second = (
            await client.post(f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]})
        ).json()

        response = await client.get(
            f"{AUTH}/me", headers={"Authorization": f"Bearer {second['access_token']}"}
        )
        assert response.status_code == 200

    async def test_replayed_token_is_rejected(self, client: AsyncClient) -> None:
        await register(client)
        first = await login(client)
        await client.post(f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]})

        replay = await client.post(
            f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]}
        )
        assert replay.status_code == 401

    async def test_reuse_kills_the_whole_family(self, client: AsyncClient) -> None:
        """Theft detection, end to end.

        The attacker replays a stolen, already-rotated token. That is the signal. The entire
        rotation chain is revoked — including the token the legitimate user is holding — so the
        real user is forced to sign in again and the attacker gains nothing.
        """
        await register(client)
        first = await login(client)
        second = (
            await client.post(f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]})
        ).json()

        # Attacker replays the spent token.
        assert (
            await client.post(f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]})
        ).status_code == 401

        # The legitimate user's live token is now dead too.
        assert (
            await client.post(f"{AUTH}/refresh", json={"refresh_token": second["refresh_token"]})
        ).status_code == 401

    async def test_unknown_refresh_token_returns_401(self, client: AsyncClient) -> None:
        response = await client.post(
            f"{AUTH}/refresh", json={"refresh_token": "never-issued-by-us"}
        )
        assert response.status_code == 401

    async def test_sessions_are_independent(self, client: AsyncClient) -> None:
        await register(client)
        phone = await login(client)
        laptop = await login(client)

        await client.post(f"{AUTH}/refresh", json={"refresh_token": phone["refresh_token"]})
        await client.post(f"{AUTH}/refresh", json={"refresh_token": phone["refresh_token"]})

        # The laptop session survives the phone's compromise.
        assert (
            await client.post(f"{AUTH}/refresh", json={"refresh_token": laptop["refresh_token"]})
        ).status_code == 200


class TestLogout:
    async def test_logout_invalidates_the_session(self, client: AsyncClient) -> None:
        await register(client)
        tokens = await login(client)

        assert (
            await client.post(f"{AUTH}/logout", json={"refresh_token": tokens["refresh_token"]})
        ).status_code == 204

        assert (
            await client.post(f"{AUTH}/refresh", json={"refresh_token": tokens["refresh_token"]})
        ).status_code == 401

    async def test_logout_is_idempotent(self, client: AsyncClient) -> None:
        # Never confirms whether a token existed — otherwise it becomes a guessing oracle.
        response = await client.post(f"{AUTH}/logout", json={"refresh_token": "never-issued"})
        assert response.status_code == 204


class TestOpenApiSurface:
    async def test_auth_routes_are_documented(self, client: AsyncClient) -> None:
        paths = (await client.get("/openapi.json")).json()["paths"]

        for route in ("register", "login", "refresh", "logout", "me"):
            assert f"{AUTH}/{route}" in paths
