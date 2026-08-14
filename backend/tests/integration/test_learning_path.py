"""Learning-path endpoints against the real graph seeded by migration 0007.

The unit tests prove the algorithm. These prove the seeded edges reached the database and that
the whole chain — job → required skills → user profile → graph → ordered plan — holds together.
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

# Names Kubernetes but never Linux or Docker — the case a keyword list cannot handle.
DEVOPS_JOB = (
    "Platform engineer wanted. You will run our production Kubernetes clusters "
    "and own the deployment pipeline end to end. Strong ownership expected."
)


class RecordingDispatcher:
    def __init__(self) -> None:
        self.enqueued: list[uuid.UUID] = []
        self.embeddings_enqueued: list[uuid.UUID] = []

    def enqueue_resume_parse(self, resume_id: uuid.UUID) -> None:
        self.enqueued.append(resume_id)

    def enqueue_job_embedding(self, job_id: uuid.UUID) -> None:
        self.embeddings_enqueued.append(job_id)


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


async def login(client: AsyncClient) -> dict[str, str]:
    email = f"path-{uuid.uuid4().hex[:8]}@example.com"
    await client.post(f"{AUTH}/register", json={"email": email, "password": PASSWORD})
    response = await client.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def skill_id_for(client: AsyncClient, name: str) -> str:
    skill = next(s for s in (await client.get(SKILLS)).json() if s["canonical_name"] == name)
    identifier: str = skill["id"]
    return identifier


async def learn(client: AsyncClient, headers: dict[str, str], *names: str) -> None:
    for name in names:
        await client.post(
            f"{SKILLS}/me", headers=headers, json={"skill_id": await skill_id_for(client, name)}
        )


async def make_job(client: AsyncClient, headers: dict[str, str], description: str) -> str:
    response = await client.post(
        JOBS, headers=headers, json={"title": "Platform Engineer", "description": description}
    )
    job_id: str = response.json()["id"]
    return job_id


class TestJobLearningPath:
    async def test_returns_an_ordered_plan(self, client: AsyncClient) -> None:
        headers = await login(client)
        job_id = await make_job(client, headers, DEVOPS_JOB)

        response = await client.get(f"{JOBS}/{job_id}/learning-path", headers=headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["step_count"] > 0
        assert [s["order"] for s in body["steps"]] == list(range(1, body["step_count"] + 1))

    async def test_pulls_in_prerequisites_the_posting_never_mentioned(
        self, client: AsyncClient
    ) -> None:
        """The claim the whole phase exists to support.

        The description says "Kubernetes" and nothing else. The plan must still include Docker
        and Linux, in that order, because the graph knows they come first.
        """
        headers = await login(client)
        job_id = await make_job(client, headers, DEVOPS_JOB)

        body = (await client.get(f"{JOBS}/{job_id}/learning-path", headers=headers)).json()
        names = [s["canonical_name"] for s in body["steps"]]

        assert "Kubernetes" in names
        assert "Docker" in names
        assert "Linux" in names
        assert names.index("Linux") < names.index("Docker") < names.index("Kubernetes")

    async def test_unmentioned_prerequisites_are_flagged_as_such(self, client: AsyncClient) -> None:
        headers = await login(client)
        job_id = await make_job(client, headers, DEVOPS_JOB)

        body = (await client.get(f"{JOBS}/{job_id}/learning-path", headers=headers)).json()
        by_name = {s["canonical_name"]: s["directly_required"] for s in body["steps"]}

        assert by_name["Kubernetes"] is True  # the posting asked for it
        assert by_name["Linux"] is False  # the graph inferred it

    async def test_every_step_lists_what_unlocks_it(self, client: AsyncClient) -> None:
        headers = await login(client)
        job_id = await make_job(client, headers, DEVOPS_JOB)

        body = (await client.get(f"{JOBS}/{job_id}/learning-path", headers=headers)).json()
        by_name = {s["canonical_name"]: s["unlocked_by"] for s in body["steps"]}

        assert by_name["Linux"] == []
        assert "Linux" in by_name["Docker"]

    async def test_ordering_respects_every_dependency(self, client: AsyncClient) -> None:
        # The topological guarantee, asserted end to end: nothing appears before something it
        # depends on.
        headers = await login(client)
        job_id = await make_job(client, headers, DEVOPS_JOB)

        body = (await client.get(f"{JOBS}/{job_id}/learning-path", headers=headers)).json()
        position = {s["canonical_name"]: s["order"] for s in body["steps"]}

        for step in body["steps"]:
            for prerequisite in step["unlocked_by"]:
                assert position[prerequisite] < step["order"]

    async def test_known_skills_are_not_re_taught(self, client: AsyncClient) -> None:
        headers = await login(client)
        job_id = await make_job(client, headers, DEVOPS_JOB)
        await learn(client, headers, "Linux", "Docker")

        body = (await client.get(f"{JOBS}/{job_id}/learning-path", headers=headers)).json()
        names = [s["canonical_name"] for s in body["steps"]]

        assert "Linux" not in names
        assert "Docker" not in names
        assert "Kubernetes" in names

    async def test_learning_a_prerequisite_shortens_the_plan(self, client: AsyncClient) -> None:
        headers = await login(client)
        job_id = await make_job(client, headers, DEVOPS_JOB)
        before = (await client.get(f"{JOBS}/{job_id}/learning-path", headers=headers)).json()[
            "step_count"
        ]

        await learn(client, headers, "Linux")
        after = (await client.get(f"{JOBS}/{job_id}/learning-path", headers=headers)).json()[
            "step_count"
        ]

        assert after == before - 1

    async def test_total_effort_falls_as_skills_are_acquired(self, client: AsyncClient) -> None:
        headers = await login(client)
        job_id = await make_job(client, headers, DEVOPS_JOB)
        before = (await client.get(f"{JOBS}/{job_id}/learning-path", headers=headers)).json()[
            "total_effort"
        ]

        await learn(client, headers, "Linux", "Docker")
        after = (await client.get(f"{JOBS}/{job_id}/learning-path", headers=headers)).json()[
            "total_effort"
        ]

        assert after < before

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        headers = await login(client)
        job_id = await make_job(client, headers, DEVOPS_JOB)
        assert (await client.get(f"{JOBS}/{job_id}/learning-path")).status_code == 401

    async def test_another_users_private_job_is_404(self, client: AsyncClient) -> None:
        alice = await login(client)
        bob = await login(client)
        job_id = await make_job(client, alice, DEVOPS_JOB)

        response = await client.get(f"{JOBS}/{job_id}/learning-path", headers=bob)
        assert response.status_code == 404

    async def test_unknown_job_is_404(self, client: AsyncClient) -> None:
        headers = await login(client)
        response = await client.get(f"{JOBS}/{uuid.uuid4()}/learning-path", headers=headers)
        assert response.status_code == 404


class TestSkillLearningPath:
    async def test_returns_a_plan_and_a_route(self, client: AsyncClient) -> None:
        headers = await login(client)
        target = await skill_id_for(client, "Kubernetes")

        body = (await client.get(f"{SKILLS}/{target}/learning-path", headers=headers)).json()

        assert [s["canonical_name"] for s in body["steps"]][-1] == "Kubernetes"
        assert body["shortest_route"][-1] == "Kubernetes"

    async def test_the_route_starts_from_what_you_know(self, client: AsyncClient) -> None:
        headers = await login(client)
        await learn(client, headers, "Docker")
        target = await skill_id_for(client, "Kubernetes")

        body = (await client.get(f"{SKILLS}/{target}/learning-path", headers=headers)).json()

        assert body["shortest_route"][0] == "Docker"

    async def test_an_already_known_skill_needs_no_steps(self, client: AsyncClient) -> None:
        headers = await login(client)
        await learn(client, headers, "Docker")
        target = await skill_id_for(client, "Docker")

        body = (await client.get(f"{SKILLS}/{target}/learning-path", headers=headers)).json()

        assert body["step_count"] == 0

    async def test_unknown_skill_is_404(self, client: AsyncClient) -> None:
        headers = await login(client)
        response = await client.get(f"{SKILLS}/{uuid.uuid4()}/learning-path", headers=headers)
        assert response.status_code == 404


class TestSeededGraph:
    async def test_the_edges_reached_the_database(self, client: AsyncClient) -> None:
        # If migration 0007 had not seeded, every plan would be a single step with no
        # prerequisites — technically valid and completely useless.
        headers = await login(client)
        target = await skill_id_for(client, "Kubernetes")

        body = (await client.get(f"{SKILLS}/{target}/learning-path", headers=headers)).json()

        assert body["step_count"] > 1
