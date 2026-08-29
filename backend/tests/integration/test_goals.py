"""Career goals through the real HTTP stack and database.

The unit tests cover the scoring rules; these cover what only a real stack proves — that the
partial unique index really does stop a second active goal, that the status codes are the ones
the frontend branches on, and that one user cannot touch another's goal.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_task_dispatcher
from app.main import create_app

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
AUTH = "/api/v1/auth"
SKILLS = "/api/v1/skills"
JOBS = "/api/v1/jobs"
GOALS = "/api/v1/goals"

JOB_DESCRIPTION = (
    "We are hiring a backend engineer to build REST APIs with FastAPI and Python. "
    "You will work with PostgreSQL and Redis, containerise services with Docker, "
    "and deploy to AWS. Experience with Kubernetes and CI/CD is a strong plus."
)


class RecordingDispatcher:
    def enqueue_resume_parse(self, resume_id: uuid.UUID) -> None:
        pass

    def enqueue_job_embedding(self, job_id: uuid.UUID) -> None:
        pass


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app: FastAPI = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_task_dispatcher] = RecordingDispatcher
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


async def register_and_login(client: AsyncClient) -> dict[str, str]:
    email = f"goal-{uuid.uuid4().hex[:8]}@example.com"
    registered = await client.post(f"{AUTH}/register", json={"email": email, "password": PASSWORD})
    await client.post(
        f"{AUTH}/verify-email", json={"token": registered.json()["dev_verification_token"]}
    )
    tokens = (
        await client.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    ).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def create_job(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        JOBS,
        json={"title": "Backend Engineer", "description": JOB_DESCRIPTION},
        headers=headers,
    )
    assert response.status_code == 201
    return str(response.json()["id"])


class TestNoGoalYet:
    async def test_current_returns_null_not_404(self, client: AsyncClient) -> None:
        """A new account has no goal, and that is normal — not an error.

        The frontend renders "set your first goal" from this; a 404 would make the most
        common first-visit case look like a failure.
        """
        headers = await register_and_login(client)
        response = await client.get(f"{GOALS}/current", headers=headers)

        assert response.status_code == 200
        assert response.json() is None

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get(f"{GOALS}/current")).status_code == 401


class TestSettingAGoal:
    async def test_creates_a_goal_with_a_frozen_baseline(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        job_id = await create_job(client, headers)

        response = await client.post(GOALS, json={"job_id": job_id}, headers=headers)

        assert response.status_code == 201
        body = response.json()
        assert body["job"]["id"] == job_id
        assert body["baseline_score"] == body["current_score"]
        assert body["delta"] == 0.0
        assert body["achieved_at"] is None

    async def test_the_database_refuses_a_second_active_goal(self, client: AsyncClient) -> None:
        """Backed by a partial unique index, not just an application check."""
        headers = await register_and_login(client)
        first = await create_job(client, headers)
        second = await create_job(client, headers)

        await client.post(GOALS, json={"job_id": first}, headers=headers)
        response = await client.post(GOALS, json={"job_id": second}, headers=headers)

        assert response.status_code == 409

    async def test_cannot_target_someone_elses_private_job(self, client: AsyncClient) -> None:
        owner = await register_and_login(client)
        job_id = await create_job(client, owner)

        stranger = await register_and_login(client)
        response = await client.post(GOALS, json={"job_id": job_id}, headers=stranger)

        assert response.status_code == 404


class TestTheProgressLoop:
    async def test_learning_a_skill_does_not_move_the_score(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        job_id = await create_job(client, headers)
        created = (await client.post(GOALS, json={"job_id": job_id}, headers=headers)).json()

        missing = created["missing"]
        assert missing, "the seeded job description should leave gaps for a blank profile"

        started = await client.post(
            f"{SKILLS}/me/learning", json={"skill_id": missing[0]["skill_id"]}, headers=headers
        )
        assert started.status_code == 201
        assert started.json()["status"] == "learning"

        after = (await client.get(f"{GOALS}/current", headers=headers)).json()
        assert after["current_score"] == created["current_score"]
        assert after["learning_count"] == 1
        # The skill is still missing, but now flagged as in progress.
        flagged = next(s for s in after["missing"] if s["skill_id"] == missing[0]["skill_id"])
        assert flagged["is_learning"] is True

    async def test_confirming_a_learned_skill_raises_the_score(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        job_id = await create_job(client, headers)
        created = (await client.post(GOALS, json={"job_id": job_id}, headers=headers)).json()
        target = created["missing"][0]["skill_id"]

        await client.post(f"{SKILLS}/me/learning", json={"skill_id": target}, headers=headers)
        await client.patch(f"{SKILLS}/me/{target}", json={"status": "confirmed"}, headers=headers)

        after = (await client.get(f"{GOALS}/current", headers=headers)).json()
        assert after["current_score"] > created["current_score"]
        assert after["delta"] > 0
        assert after["baseline_score"] == created["baseline_score"], "baseline must never move"
        assert after["learning_count"] == 0

    async def test_profile_reports_learning_separately(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        job_id = await create_job(client, headers)
        created = (await client.post(GOALS, json={"job_id": job_id}, headers=headers)).json()

        await client.post(
            f"{SKILLS}/me/learning",
            json={"skill_id": created["missing"][0]["skill_id"]},
            headers=headers,
        )

        profile = (await client.get(f"{SKILLS}/me", headers=headers)).json()
        assert profile["total_learning"] == 1
        assert len(profile["learning"]) == 1
        # And it is not double-counted as something the user already has.
        assert profile["total_confirmed"] == 0


class TestAchievingAndAbandoning:
    async def test_cannot_claim_an_unreached_goal(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        job_id = await create_job(client, headers)
        goal = (await client.post(GOALS, json={"job_id": job_id}, headers=headers)).json()

        response = await client.post(f"{GOALS}/{goal['id']}/achieve", headers=headers)

        assert response.status_code == 409

    async def test_abandoning_frees_the_slot(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        first = await create_job(client, headers)
        second = await create_job(client, headers)
        goal = (await client.post(GOALS, json={"job_id": first}, headers=headers)).json()

        deleted = await client.delete(f"{GOALS}/{goal['id']}", headers=headers)
        assert deleted.status_code == 204

        assert (await client.get(f"{GOALS}/current", headers=headers)).json() is None
        retry = await client.post(GOALS, json={"job_id": second}, headers=headers)
        assert retry.status_code == 201

    async def test_cannot_abandon_someone_elses_goal(self, client: AsyncClient) -> None:
        owner = await register_and_login(client)
        job_id = await create_job(client, owner)
        goal = (await client.post(GOALS, json={"job_id": job_id}, headers=owner)).json()

        stranger = await register_and_login(client)
        response = await client.delete(f"{GOALS}/{goal['id']}", headers=stranger)

        assert response.status_code == 404
        # And the owner's goal is untouched.
        assert (await client.get(f"{GOALS}/current", headers=owner)).json() is not None

    async def test_achievements_start_empty(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        assert (await client.get(f"{GOALS}/achievements", headers=headers)).json() == []
