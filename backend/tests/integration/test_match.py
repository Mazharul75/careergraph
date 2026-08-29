"""Match scoring through the real HTTP stack.

Embeddings are absent here: the worker is not running, so `semantic_available` is False and
scoring falls back to skills alone. That is the realistic first-visit state for a user whose
resume is still parsing, and it is worth pinning down — the API must answer usefully rather
than withholding a result.
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

JOB_DESCRIPTION = (
    "Backend engineer wanted. You will build services in Python and FastAPI, "
    "backed by PostgreSQL. Docker experience essential. Docker and Docker again."
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
def dispatcher() -> RecordingDispatcher:
    return RecordingDispatcher()


@pytest.fixture
async def client(
    db_session: AsyncSession, dispatcher: RecordingDispatcher
) -> AsyncGenerator[AsyncClient, None]:
    app: FastAPI = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_task_dispatcher] = lambda: dispatcher
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


async def login(client: AsyncClient, role: str = "job_seeker") -> dict[str, str]:
    email = f"match-{uuid.uuid4().hex[:8]}@example.com"
    registered = await client.post(
        f"{AUTH}/register", json={"email": email, "password": PASSWORD, "role": role}
    )
    await client.post(
        f"{AUTH}/verify-email", json={"token": registered.json()["dev_verification_token"]}
    )
    response = await client.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def add_skill(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    skill = next(s for s in (await client.get(SKILLS)).json() if s["canonical_name"] == name)
    await client.post(f"{SKILLS}/me", headers=headers, json={"skill_id": skill["id"]})
    skill_id: str = skill["id"]
    return skill_id


async def create_job(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        JOBS,
        headers=headers,
        json={"title": "Backend Engineer", "description": JOB_DESCRIPTION},
    )
    job_id: str = response.json()["id"]
    return job_id


class TestMatchEndpoint:
    async def test_zero_skills_scores_zero(self, client: AsyncClient) -> None:
        headers = await login(client)
        job_id = await create_job(client, headers)

        body = (await client.get(f"{JOBS}/{job_id}/match", headers=headers)).json()

        assert body["score"] == 0.0
        assert body["matched"] == []
        assert body["missing"]

    async def test_acquiring_a_skill_raises_the_score(self, client: AsyncClient) -> None:
        headers = await login(client)
        job_id = await create_job(client, headers)
        before = (await client.get(f"{JOBS}/{job_id}/match", headers=headers)).json()["score"]

        await add_skill(client, headers, "Python")
        after = (await client.get(f"{JOBS}/{job_id}/match", headers=headers)).json()["score"]

        assert after > before

    async def test_matched_and_missing_are_disjoint_and_complete(self, client: AsyncClient) -> None:
        headers = await login(client)
        job_id = await create_job(client, headers)
        await add_skill(client, headers, "Python")

        body = (await client.get(f"{JOBS}/{job_id}/match", headers=headers)).json()

        matched = {s["skill_id"] for s in body["matched"]}
        missing = {s["skill_id"] for s in body["missing"]}
        assert matched & missing == set()
        assert len(matched) + len(missing) == body["total_required"]

    async def test_the_score_explains_itself(self, client: AsyncClient) -> None:
        # The product requirement: a bare percentage is not actionable.
        headers = await login(client)
        job_id = await create_job(client, headers)
        await add_skill(client, headers, "Python")

        body = (await client.get(f"{JOBS}/{job_id}/match", headers=headers)).json()

        for field in ("score", "skill_coverage", "semantic_similarity", "matched", "missing"):
            assert field in body
        assert body["matched"][0]["canonical_name"] == "Python"

    async def test_semantic_component_is_reported_unavailable(self, client: AsyncClient) -> None:
        # No worker running, so nothing is embedded. The client must be able to tell that the
        # score will change, rather than seeing it move and assuming a bug.
        headers = await login(client)
        job_id = await create_job(client, headers)

        body = (await client.get(f"{JOBS}/{job_id}/match", headers=headers)).json()

        assert body["semantic_available"] is False
        assert body["semantic_similarity"] == 0.0

    async def test_importance_weighting_is_visible(self, client: AsyncClient) -> None:
        # Docker appears three times in the description, Python once.
        headers = await login(client)
        job_id = await create_job(client, headers)

        body = (await client.get(f"{JOBS}/{job_id}/match", headers=headers)).json()
        by_name = {s["canonical_name"]: s["importance"] for s in body["missing"]}

        assert by_name["Docker"] > by_name["Python"]

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        headers = await login(client)
        job_id = await create_job(client, headers)

        assert (await client.get(f"{JOBS}/{job_id}/match")).status_code == 401

    async def test_another_users_private_job_is_404(self, client: AsyncClient) -> None:
        alice = await login(client)
        bob = await login(client)
        job_id = await create_job(client, alice)

        assert (await client.get(f"{JOBS}/{job_id}/match", headers=bob)).status_code == 404

    async def test_public_postings_can_be_matched_by_anyone(self, client: AsyncClient) -> None:
        recruiter = await login(client, role="recruiter")
        seeker = await login(client)
        response = await client.post(
            JOBS,
            headers=recruiter,
            json={
                "title": "Backend Engineer",
                "description": JOB_DESCRIPTION,
                "is_public": True,
            },
        )
        job_id = response.json()["id"]

        assert (await client.get(f"{JOBS}/{job_id}/match", headers=seeker)).status_code == 200

    async def test_unknown_job_is_404(self, client: AsyncClient) -> None:
        headers = await login(client)
        response = await client.get(f"{JOBS}/{uuid.uuid4()}/match", headers=headers)
        assert response.status_code == 404


class TestEmbeddingDispatch:
    async def test_creating_a_job_queues_an_embedding(
        self, client: AsyncClient, dispatcher: RecordingDispatcher
    ) -> None:
        headers = await login(client)
        job_id = await create_job(client, headers)

        assert dispatcher.embeddings_enqueued == [uuid.UUID(job_id)]

    async def test_editing_the_description_requeues(
        self, client: AsyncClient, dispatcher: RecordingDispatcher
    ) -> None:
        # The stored vector describes text that no longer exists.
        headers = await login(client)
        job_id = await create_job(client, headers)
        await client.patch(
            f"{JOBS}/{job_id}",
            headers=headers,
            json={"description": "A frontend role using React and TypeScript across our stack."},
        )

        assert dispatcher.embeddings_enqueued.count(uuid.UUID(job_id)) == 2

    async def test_editing_only_the_title_does_not_requeue(
        self, client: AsyncClient, dispatcher: RecordingDispatcher
    ) -> None:
        headers = await login(client)
        job_id = await create_job(client, headers)
        await client.patch(f"{JOBS}/{job_id}", headers=headers, json={"title": "Renamed"})

        assert dispatcher.embeddings_enqueued.count(uuid.UUID(job_id)) == 1
