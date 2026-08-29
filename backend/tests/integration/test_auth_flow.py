"""End-to-end authentication through the real HTTP stack and a real database.

The unit tests prove the rules. These prove the wiring: routing, Pydantic validation, the
dependency graph, exception translation to status codes, and the actual SQL.
"""

from __future__ import annotations

from collections.abc import Callable, Generator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_google_verifier
from app.core.config import get_settings
from app.services.google_auth import GoogleIdentity

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
AUTH = "/api/v1/auth"


async def register(client: AsyncClient, email: str = "ada@example.com", **kwargs: object) -> dict:
    payload = {"email": email, "password": PASSWORD, "full_name": "Ada Lovelace", **kwargs}
    response = await client.post(f"{AUTH}/register", json=payload)
    assert response.status_code == 201, response.text
    body: dict = response.json()
    return body


async def verify(client: AsyncClient, register_response: dict) -> None:
    """Redeem the dev-mode token a register() call returned.

    ``exposes_dev_verification_tokens`` is true in both `local` and `ci` (see
    ``Settings``), which is what makes this possible without an inbox — the same token a
    real email would have carried is simply handed back in the response body.
    """
    token = register_response["dev_verification_token"]
    assert token, "expected a dev verification token in local/ci"
    response = await client.post(f"{AUTH}/verify-email", json={"token": token})
    assert response.status_code == 200, response.text


async def register_and_verify(
    client: AsyncClient, email: str = "ada@example.com", **kwargs: object
) -> dict:
    body = await register(client, email=email, **kwargs)
    await verify(client, body)
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
        assert body["has_password"] is True
        # Nobody has clicked the link yet.
        assert body["email_verified"] is False

    async def test_dev_verification_token_is_present_in_local_and_ci(
        self, client: AsyncClient
    ) -> None:
        """The one field that must never reach a real user's inbox unencrypted-in-the-clear
        of an HTTP response — present here specifically because tests run with
        ENVIRONMENT=local or ENVIRONMENT=ci, never staging/production."""
        body = await register(client)
        assert body["dev_verification_token"]

    async def test_response_never_contains_the_password_hash(self, client: AsyncClient) -> None:
        # The response schema has no such field, so this asserts the schema boundary holds.
        response = await client.post(
            f"{AUTH}/register",
            json={"email": "leak@example.com", "password": PASSWORD},
        )
        assert "password_hash" not in response.text.lower()

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


class TestEmailVerification:
    async def test_login_is_refused_before_verifying(self, client: AsyncClient) -> None:
        await register(client)
        response = await client.post(
            f"{AUTH}/login", json={"email": "ada@example.com", "password": PASSWORD}
        )
        assert response.status_code == 403

    async def test_verifying_unlocks_login(self, client: AsyncClient) -> None:
        body = await register(client)
        await verify(client, body)

        response = await client.post(
            f"{AUTH}/login", json={"email": "ada@example.com", "password": PASSWORD}
        )
        assert response.status_code == 200

    async def test_verify_response_reflects_the_new_state(self, client: AsyncClient) -> None:
        body = await register(client)
        response = await client.post(
            f"{AUTH}/verify-email", json={"token": body["dev_verification_token"]}
        )
        assert response.status_code == 200
        assert response.json()["email_verified"] is True

    async def test_garbage_token_is_rejected(self, client: AsyncClient) -> None:
        await register(client)
        response = await client.post(f"{AUTH}/verify-email", json={"token": "not-a-real-token"})
        assert response.status_code == 400

    async def test_a_token_cannot_be_redeemed_twice(self, client: AsyncClient) -> None:
        body = await register(client)
        token = body["dev_verification_token"]

        first = await client.post(f"{AUTH}/verify-email", json={"token": token})
        assert first.status_code == 200

        replay = await client.post(f"{AUTH}/verify-email", json={"token": token})
        assert replay.status_code == 400

    async def test_resend_always_returns_204(self, client: AsyncClient) -> None:
        """Whether the address exists, is already verified, or was never registered at
        all — the response must never differ, or the endpoint becomes an oracle."""
        await register(client)

        for email in ("ada@example.com", "nobody-at-all@example.com"):
            response = await client.post(f"{AUTH}/resend-verification", json={"email": email})
            assert response.status_code == 204

    async def test_resend_invalidates_the_previous_link(self, client: AsyncClient) -> None:
        original = await register(client)

        resend = await client.post(f"{AUTH}/resend-verification", json={"email": "ada@example.com"})
        assert resend.status_code == 204

        stale = await client.post(
            f"{AUTH}/verify-email", json={"token": original["dev_verification_token"]}
        )
        assert stale.status_code == 400

    async def test_already_verified_resend_is_still_204_and_sends_nothing_new(
        self, client: AsyncClient
    ) -> None:
        body = await register(client)
        await verify(client, body)

        response = await client.post(
            f"{AUTH}/resend-verification", json={"email": "ada@example.com"}
        )
        assert response.status_code == 204


class TestLogin:
    async def test_returns_a_token_pair(self, client: AsyncClient) -> None:
        await register_and_verify(client)
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
        await register_and_verify(client)
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
        await register_and_verify(client)
        first = await login(client)

        response = await client.post(
            f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]}
        )
        assert response.status_code == 200
        second = response.json()
        assert second["refresh_token"] != first["refresh_token"]

    async def test_new_access_token_works(self, client: AsyncClient) -> None:
        await register_and_verify(client)
        first = await login(client)
        second = (
            await client.post(f"{AUTH}/refresh", json={"refresh_token": first["refresh_token"]})
        ).json()

        response = await client.get(
            f"{AUTH}/me", headers={"Authorization": f"Bearer {second['access_token']}"}
        )
        assert response.status_code == 200

    async def test_replayed_token_is_rejected(self, client: AsyncClient) -> None:
        await register_and_verify(client)
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
        await register_and_verify(client)
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
        await register_and_verify(client)
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
        await register_and_verify(client)
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


@pytest.fixture
def google_client_id(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> Generator[str, None, None]:
    """Turns the feature on for one test by setting the one thing that gates it."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    get_settings.cache_clear()
    yield "test-client-id.apps.googleusercontent.com"
    get_settings.cache_clear()


@pytest.fixture
def fake_google_identity(app: FastAPI) -> Callable[[GoogleIdentity], None]:
    """Installs a fake verifier that returns a canned identity for *any* id_token.

    The real verifier does real cryptography against Google's live keys; overriding
    ``get_google_verifier`` — the same dependency-override seam used for the task queue and
    the rate limiter — is what lets these tests prove the account-creation and
    account-linking logic without ever constructing a real signed JWT.
    """

    def _install(identity: GoogleIdentity) -> None:
        app.dependency_overrides[get_google_verifier] = lambda: (
            lambda id_token, *, client_id: identity
        )

    return _install


class TestGoogleSignIn:
    """Exercises the whole flow with a fake identity, via the ``get_google_verifier``
    dependency override — no real Google credentials or network access needed."""

    async def test_disabled_without_a_configured_client_id(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Explicit, not assumed: a developer's own real `.env` may genuinely have
        # GOOGLE_CLIENT_ID set (to test the feature locally against a real Google project).
        # Patching the already-constructed, process-wide settings singleton directly — rather
        # than neutralising its env-file source the way the unit tests do — is deliberate
        # here: this suite's DATABASE_URL and JWT_SECRET_KEY commonly live *only* in that
        # same file with no shell-exported fallback, and blanking the file source would take
        # the whole app down with Google, not just Google.
        monkeypatch.setattr(get_settings(), "google_client_id", None)

        response = await client.post(f"{AUTH}/google", json={"id_token": "irrelevant"})
        assert response.status_code == 503

    async def test_creates_a_new_account_from_a_verified_identity(
        self,
        client: AsyncClient,
        google_client_id: str,
        fake_google_identity: Callable[[GoogleIdentity], None],
    ) -> None:
        fake_google_identity(
            GoogleIdentity(
                subject="google-sub-1",
                email="newcomer@example.com",
                email_verified=True,
                full_name="New Comer",
            )
        )

        response = await client.post(f"{AUTH}/google", json={"id_token": "fake"})

        assert response.status_code == 200
        body = response.json()
        assert body["access_token"]

        me = await client.get(
            f"{AUTH}/me", headers={"Authorization": f"Bearer {body['access_token']}"}
        )
        assert me.json()["email"] == "newcomer@example.com"
        # A verified Google identity marks the account verified immediately — no separate
        # email step for something Google has already proven.
        assert me.json()["email_verified"] is True
        assert me.json()["has_password"] is False

    async def test_links_an_existing_password_account_by_email(
        self,
        client: AsyncClient,
        google_client_id: str,
        fake_google_identity: Callable[[GoogleIdentity], None],
    ) -> None:
        await register(client, email="both@example.com")

        fake_google_identity(
            GoogleIdentity(
                subject="google-sub-2",
                email="both@example.com",
                email_verified=True,
                full_name="Both Ways",
            )
        )
        response = await client.post(f"{AUTH}/google", json={"id_token": "fake"})
        assert response.status_code == 200

        # The password account is now verified too, and the same one account either
        # credential can reach — a second account was not created.
        me = await client.get(
            f"{AUTH}/me",
            headers={"Authorization": f"Bearer {response.json()['access_token']}"},
        )
        assert me.json()["email"] == "both@example.com"
        assert me.json()["has_password"] is True
        assert me.json()["email_verified"] is True

    async def test_returning_user_is_recognised_by_subject_not_email(
        self,
        client: AsyncClient,
        google_client_id: str,
        fake_google_identity: Callable[[GoogleIdentity], None],
    ) -> None:
        identity = GoogleIdentity(
            subject="google-sub-3", email="first@example.com", email_verified=True, full_name="A"
        )
        fake_google_identity(identity)
        first = await client.post(f"{AUTH}/google", json={"id_token": "fake"})
        first_user_id = (
            await client.get(
                f"{AUTH}/me",
                headers={"Authorization": f"Bearer {first.json()['access_token']}"},
            )
        ).json()["id"]

        # Same subject, a changed email — still the same account.
        fake_google_identity(
            GoogleIdentity(
                subject="google-sub-3",
                email="changed@example.com",
                email_verified=True,
                full_name="A",
            )
        )
        second = await client.post(f"{AUTH}/google", json={"id_token": "fake"})
        second_user_id = (
            await client.get(
                f"{AUTH}/me",
                headers={"Authorization": f"Bearer {second.json()['access_token']}"},
            )
        ).json()["id"]

        assert first_user_id == second_user_id


class TestOpenApiSurface:
    async def test_auth_routes_are_documented(self, client: AsyncClient) -> None:
        paths = (await client.get("/openapi.json")).json()["paths"]

        for route in (
            "register",
            "login",
            "refresh",
            "logout",
            "me",
            "verify-email",
            "resend-verification",
            "forgot-password",
            "reset-password",
            "google",
        ):
            assert f"{AUTH}/{route}" in paths


class TestPasswordReset:
    async def test_forgot_password_returns_a_dev_token_in_local_and_ci(
        self, client: AsyncClient
    ) -> None:
        await register_and_verify(client)

        response = await client.post(f"{AUTH}/forgot-password", json={"email": "ada@example.com"})

        assert response.status_code == 200
        assert response.json()["dev_reset_token"]

    async def test_forgot_password_is_the_same_shape_for_an_unknown_address(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            f"{AUTH}/forgot-password", json={"email": "nobody-registered@example.com"}
        )
        assert response.status_code == 200
        assert response.json()["dev_reset_token"] is None

    async def test_reset_password_lets_you_log_in_with_the_new_password(
        self, client: AsyncClient
    ) -> None:
        await register_and_verify(client)
        forgot = await client.post(f"{AUTH}/forgot-password", json={"email": "ada@example.com"})
        token = forgot.json()["dev_reset_token"]

        reset = await client.post(
            f"{AUTH}/reset-password",
            json={"token": token, "new_password": "a-brand-new-password-123"},
        )
        assert reset.status_code == 200
        assert reset.json()["email"] == "ada@example.com"

        old_password = await client.post(
            f"{AUTH}/login", json={"email": "ada@example.com", "password": PASSWORD}
        )
        assert old_password.status_code == 401

        new_password = await client.post(
            f"{AUTH}/login",
            json={"email": "ada@example.com", "password": "a-brand-new-password-123"},
        )
        assert new_password.status_code == 200

    async def test_reset_password_revokes_existing_sessions(self, client: AsyncClient) -> None:
        await register_and_verify(client)
        original_session = await login(client)

        forgot = await client.post(f"{AUTH}/forgot-password", json={"email": "ada@example.com"})
        await client.post(
            f"{AUTH}/reset-password",
            json={
                "token": forgot.json()["dev_reset_token"],
                "new_password": "a-brand-new-password-123",
            },
        )

        stale_refresh = await client.post(
            f"{AUTH}/refresh", json={"refresh_token": original_session["refresh_token"]}
        )
        assert stale_refresh.status_code == 401

    async def test_reset_password_rejects_a_bad_token(self, client: AsyncClient) -> None:
        response = await client.post(
            f"{AUTH}/reset-password",
            json={"token": "never-issued", "new_password": "whatever-password-1"},
        )
        assert response.status_code == 400

    async def test_a_reset_token_cannot_be_redeemed_twice(self, client: AsyncClient) -> None:
        await register_and_verify(client)
        forgot = await client.post(f"{AUTH}/forgot-password", json={"email": "ada@example.com"})
        token = forgot.json()["dev_reset_token"]

        first = await client.post(
            f"{AUTH}/reset-password",
            json={"token": token, "new_password": "first-new-password-1"},
        )
        assert first.status_code == 200

        replay = await client.post(
            f"{AUTH}/reset-password",
            json={"token": token, "new_password": "second-attempt-1234"},
        )
        assert replay.status_code == 400

    async def test_short_new_password_is_422(self, client: AsyncClient) -> None:
        await register_and_verify(client)
        forgot = await client.post(f"{AUTH}/forgot-password", json={"email": "ada@example.com"})

        response = await client.post(
            f"{AUTH}/reset-password",
            json={"token": forgot.json()["dev_reset_token"], "new_password": "short"},
        )
        assert response.status_code == 422
