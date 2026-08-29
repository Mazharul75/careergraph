"""Candidate ranking and admin routes through the real stack.

Both surfaces are defined mostly by what they *refuse*, so most of these tests assert a
rejection. That is deliberate: an authorization bug is invisible when you only test the
happy path.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_task_dispatcher
from app.main import create_app

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
AUTH = "/api/v1/auth"
SKILLS = "/api/v1/skills"
JOBS = "/api/v1/jobs"
ADMIN = "/api/v1/admin"

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


async def register(client: AsyncClient, role: str = "job_seeker") -> tuple[dict[str, str], str]:
    email = f"{role}-{uuid.uuid4().hex[:8]}@example.com"
    registered = await client.post(
        f"{AUTH}/register", json={"email": email, "password": PASSWORD, "role": role}
    )
    await client.post(
        f"{AUTH}/verify-email", json={"token": registered.json()["dev_verification_token"]}
    )
    tokens = (
        await client.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    ).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}, email


async def make_admin(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    """Promote via SQL, mirroring scripts/promote_admin.py.

    There is deliberately no API route that grants admin, so a test cannot create one through
    the app either — which is the property being relied on.
    """
    headers, email = await register(client)
    await session.execute(
        text("UPDATE users SET role = 'admin' WHERE email = :email"), {"email": email}
    )
    await session.commit()
    return headers


async def create_job(client: AsyncClient, headers: dict[str, str], public: bool = False) -> str:
    response = await client.post(
        JOBS,
        json={
            "title": "Backend Engineer",
            "description": JOB_DESCRIPTION,
            "is_public": public,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return str(response.json()["id"])


class TestCandidateRanking:
    async def test_job_seekers_cannot_rank_candidates(self, client: AsyncClient) -> None:
        """The talent pool is not readable by the people in it."""
        seeker, _ = await register(client)
        job_id = await create_job(client, seeker)

        response = await client.get(f"{JOBS}/{job_id}/candidates", headers=seeker)

        assert response.status_code == 403

    async def test_recruiter_sees_ranked_candidates_for_their_own_job(
        self, client: AsyncClient
    ) -> None:
        candidate, _ = await register(client)
        python = next(
            s for s in (await client.get(SKILLS)).json() if s["canonical_name"] == "Python"
        )
        docker = next(
            s for s in (await client.get(SKILLS)).json() if s["canonical_name"] == "Docker"
        )
        for skill in (python, docker):
            await client.post(f"{SKILLS}/me", json={"skill_id": skill["id"]}, headers=candidate)

        recruiter, _ = await register(client, role="recruiter")
        job_id = await create_job(client, recruiter, public=True)

        response = await client.get(f"{JOBS}/{job_id}/candidates", headers=recruiter)

        assert response.status_code == 200
        ranked = response.json()
        assert ranked, "a candidate holding two required skills should appear"
        top = ranked[0]
        assert top["score"] > 0
        # The score ships with its reasoning, same contract as the job-seeker match.
        assert top["matched"], "a ranked candidate must show why they ranked"
        assert "email" not in top, "a ranking must not hand over contact details"

    async def test_scores_are_sorted_descending(self, client: AsyncClient) -> None:
        vocabulary = (await client.get(SKILLS)).json()
        wanted = [
            s for s in vocabulary if s["canonical_name"] in ("Python", "Docker", "PostgreSQL")
        ]

        strong, _ = await register(client)
        for skill in wanted:
            await client.post(f"{SKILLS}/me", json={"skill_id": skill["id"]}, headers=strong)

        weak, _ = await register(client)
        await client.post(f"{SKILLS}/me", json={"skill_id": wanted[0]["id"]}, headers=weak)

        recruiter, _ = await register(client, role="recruiter")
        job_id = await create_job(client, recruiter, public=True)

        ranked = (await client.get(f"{JOBS}/{job_id}/candidates", headers=recruiter)).json()
        scores = [c["score"] for c in ranked]
        assert scores == sorted(scores, reverse=True)

    async def test_cannot_rank_against_someone_elses_posting(self, client: AsyncClient) -> None:
        """Otherwise any public job id becomes a directory of every candidate."""
        owner, _ = await register(client, role="recruiter")
        job_id = await create_job(client, owner, public=True)

        other, _ = await register(client, role="recruiter")
        response = await client.get(f"{JOBS}/{job_id}/candidates", headers=other)

        assert response.status_code == 404

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get(f"{JOBS}/{uuid.uuid4()}/candidates")).status_code == 401


class TestAdminAccess:
    async def test_job_seeker_is_refused(self, client: AsyncClient) -> None:
        headers, _ = await register(client)
        assert (await client.get(f"{ADMIN}/stats", headers=headers)).status_code == 403

    async def test_recruiter_is_refused(self, client: AsyncClient) -> None:
        headers, _ = await register(client, role="recruiter")
        assert (await client.get(f"{ADMIN}/users", headers=headers)).status_code == 403

    async def test_anonymous_is_refused(self, client: AsyncClient) -> None:
        assert (await client.get(f"{ADMIN}/stats")).status_code == 401

    async def test_registration_cannot_grant_admin(self, client: AsyncClient) -> None:
        """The single most important test in this file.

        ``RegisterRequest.role`` is a Literal of the two non-privileged roles, so a crafted
        signup claiming admin is rejected by validation before it reaches any code.
        """
        response = await client.post(
            f"{AUTH}/register",
            json={
                "email": f"sneaky-{uuid.uuid4().hex[:8]}@example.com",
                "password": PASSWORD,
                "role": "admin",
            },
        )
        assert response.status_code == 422


class TestAdminActions:
    async def test_admin_sees_system_stats(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await make_admin(client, db_session)

        body = (await client.get(f"{ADMIN}/stats", headers=headers)).json()

        assert body["total_users"] >= 1
        assert body["admins"] >= 1
        assert "total_jobs" in body and "resumes_failed" in body

    async def test_admin_lists_users_without_password_hashes(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await make_admin(client, db_session)

        users = (await client.get(f"{ADMIN}/users", headers=headers)).json()

        assert users
        assert "password_hash" not in users[0]
        assert {"id", "email", "role", "is_active"} <= set(users[0])

    async def test_admin_can_suspend_another_account(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        victim, victim_email = await register(client)
        headers = await make_admin(client, db_session)
        users = (await client.get(f"{ADMIN}/users", headers=headers)).json()
        target = next(u for u in users if u["email"] == victim_email)

        response = await client.patch(
            f"{ADMIN}/users/{target['id']}/active", json={"is_active": False}, headers=headers
        )

        assert response.status_code == 200
        assert response.json()["is_active"] is False
        # A suspension must bite immediately, not when the existing token expires.
        assert (await client.get(f"{AUTH}/me", headers=victim)).status_code == 401

    async def test_admin_cannot_suspend_themselves(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers = await make_admin(client, db_session)
        me = (await client.get(f"{AUTH}/me", headers=headers)).json()

        response = await client.patch(
            f"{ADMIN}/users/{me['id']}/active", json={"is_active": False}, headers=headers
        )

        assert response.status_code == 409

    async def test_refuses_to_demote_the_last_admin(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Otherwise the system can be left with nobody able to administer it."""
        headers = await make_admin(client, db_session)
        me = (await client.get(f"{AUTH}/me", headers=headers)).json()

        response = await client.patch(
            f"{ADMIN}/users/{me['id']}/role", json={"role": "job_seeker"}, headers=headers
        )

        assert response.status_code == 409


class TestScoringWithEmbeddedResumes:
    """Regression: every scoring path once a resume actually has an embedding.

    The original candidate-ranking tests passed while being blind to a 500, because no test
    resume ever had an embedding — and every caller checks the *resume* embedding before it
    reads ``job.embedding``. With that short-circuit always taken, the deferred column on Job
    was never touched. In production, the moment the worker finished its first embedding,
    both ``/match`` and ``/candidates`` began returning 500.

    Setting an embedding directly here, rather than running the real model, keeps the test
    fast and deterministic while exercising the exact code path that broke.
    """

    @staticmethod
    async def _give_resume_an_embedding(session: AsyncSession, user_email: str) -> None:
        vector = "[" + ",".join(["0.05"] * 384) + "]"
        await session.execute(
            text(
                "INSERT INTO resumes (id, user_id, original_filename, content_type, "
                "size_bytes, status, extracted_text, embedding) "
                "SELECT gen_random_uuid(), id, 'demo.pdf', 'application/pdf', 1024, "
                "'complete', 'Python PostgreSQL Docker', CAST(:vec AS vector) "
                "FROM users WHERE email = :email"
            ),
            {"vec": vector, "email": user_email},
        )
        await session.commit()

    async def test_match_works_when_the_resume_is_embedded(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        headers, email = await register(client)
        job_id = await create_job(client, headers)
        await self._give_resume_an_embedding(db_session, email)

        response = await client.get(f"{JOBS}/{job_id}/match", headers=headers)

        assert response.status_code == 200, response.text

    async def test_candidate_ranking_works_when_resumes_are_embedded(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        candidate, candidate_email = await register(client)
        python = next(
            s for s in (await client.get(SKILLS)).json() if s["canonical_name"] == "Python"
        )
        await client.post(f"{SKILLS}/me", json={"skill_id": python["id"]}, headers=candidate)
        await self._give_resume_an_embedding(db_session, candidate_email)

        recruiter, _ = await register(client, role="recruiter")
        job_id = await create_job(client, recruiter, public=True)

        response = await client.get(f"{JOBS}/{job_id}/candidates", headers=recruiter)

        assert response.status_code == 200, response.text
