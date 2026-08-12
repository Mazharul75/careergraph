"""Role-based authorization.

`require_role` has no consumer in the production routes yet — recruiter-only endpoints arrive
in Phase 2. Testing it now against throwaway routes mounted on the real app means the
authorization primitive is proven before anything depends on it, rather than being debugged
later while also debugging the feature that uses it.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_role
from app.main import create_app
from app.models.user import User, UserRole

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
AUTH = "/api/v1/auth"


@pytest.fixture
async def app_with_guarded_routes(db_session: AsyncSession) -> FastAPI:
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    @app.get("/test/recruiter-only")
    async def _recruiter_only(
        user: User = Depends(require_role(UserRole.RECRUITER)),
    ) -> dict[str, str]:
        return {"role": user.role.value}

    @app.get("/test/seeker-only")
    async def _seeker_only(
        user: User = Depends(require_role(UserRole.JOB_SEEKER)),
    ) -> dict[str, str]:
        return {"role": user.role.value}

    @app.get("/test/any-authenticated")
    async def _any_authenticated(user: CurrentUser) -> dict[str, str]:
        return {"role": user.role.value}

    return app


@pytest.fixture
async def guarded_client(app_with_guarded_routes: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app_with_guarded_routes)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def token_for(client: AsyncClient, email: str, role: str) -> str:
    await client.post(f"{AUTH}/register", json={"email": email, "password": PASSWORD, "role": role})
    response = await client.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    return response.json()["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestRoleEnforcement:
    async def test_matching_role_is_allowed(self, guarded_client: AsyncClient) -> None:
        token = await token_for(guarded_client, "r@example.com", "recruiter")

        response = await guarded_client.get("/test/recruiter-only", headers=bearer(token))
        assert response.status_code == 200
        assert response.json()["role"] == "recruiter"

    async def test_wrong_role_is_forbidden(self, guarded_client: AsyncClient) -> None:
        token = await token_for(guarded_client, "s@example.com", "job_seeker")

        response = await guarded_client.get("/test/recruiter-only", headers=bearer(token))
        # 403, not 401: identity was proven, permission was not granted. A 401 would tell the
        # client to re-authenticate, which would not help and would loop.
        assert response.status_code == 403

    async def test_enforcement_runs_in_both_directions(self, guarded_client: AsyncClient) -> None:
        recruiter = await token_for(guarded_client, "r2@example.com", "recruiter")

        assert (
            await guarded_client.get("/test/seeker-only", headers=bearer(recruiter))
        ).status_code == 403

    async def test_any_role_passes_a_plain_authentication_check(
        self, guarded_client: AsyncClient
    ) -> None:
        for email, role in (("a@example.com", "job_seeker"), ("b@example.com", "recruiter")):
            token = await token_for(guarded_client, email, role)
            response = await guarded_client.get("/test/any-authenticated", headers=bearer(token))
            assert response.status_code == 200

    async def test_unauthenticated_request_is_401_not_403(
        self, guarded_client: AsyncClient
    ) -> None:
        # Authentication is checked before authorization: with no identity there is nothing to
        # authorize, so the answer is "log in", not "you may not".
        assert (await guarded_client.get("/test/recruiter-only")).status_code == 401
