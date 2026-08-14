"""Skill profile and job routes through the real HTTP stack and database.

Covers the two things that only show up against real infrastructure: the seed migration
actually populating 113 skills, and the recruiter role guard actually rejecting a job seeker.
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
from app.services.extraction import PDF_CONTENT_TYPE
from tests.unit.test_extraction import make_pdf

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
AUTH = "/api/v1/auth"
SKILLS = "/api/v1/skills"
JOBS = "/api/v1/jobs"

JOB_DESCRIPTION = (
    "We are hiring a backend engineer to build REST APIs with FastAPI and Python. "
    "You will work with PostgreSQL and Redis, containerise services with Docker, "
    "and deploy to AWS. Experience with Kubernetes and CI/CD is a strong plus. "
    "Docker experience is essential. Docker, Docker, and more Docker."
)


class RecordingDispatcher:
    def __init__(self) -> None:
        self.enqueued: list[uuid.UUID] = []

    def enqueue_resume_parse(self, resume_id: uuid.UUID) -> None:
        self.enqueued.append(resume_id)


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


async def register_and_login(client: AsyncClient, role: str = "job_seeker") -> dict[str, str]:
    email = f"{role}-{uuid.uuid4().hex[:8]}@example.com"
    await client.post(f"{AUTH}/register", json={"email": email, "password": PASSWORD, "role": role})
    tokens = (
        await client.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    ).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


class TestVocabulary:
    async def test_seed_migration_populated_the_vocabulary(self, client: AsyncClient) -> None:
        # Proves the data migration ran, not just the schema migration.
        skills = (await client.get(SKILLS)).json()
        assert len(skills) == 113

    async def test_vocabulary_is_public(self, client: AsyncClient) -> None:
        # The frontend needs it to render a skill picker before anyone has signed in.
        assert (await client.get(SKILLS)).status_code == 200

    async def test_can_filter_by_category(self, client: AsyncClient) -> None:
        languages = (await client.get(f"{SKILLS}?category=language")).json()
        assert languages
        assert all(s["category"] == "language" for s in languages)

    async def test_known_skills_are_present(self, client: AsyncClient) -> None:
        names = {s["canonical_name"] for s in (await client.get(SKILLS)).json()}
        for expected in ("Python", "PostgreSQL", "Docker", "Kubernetes", "C++", "Go"):
            assert expected in names


class TestSkillProfile:
    async def test_profile_starts_empty(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        body = (await client.get(f"{SKILLS}/me", headers=headers)).json()

        assert body["total_confirmed"] == 0
        assert body["total_suggested"] == 0

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get(f"{SKILLS}/me")).status_code == 401

    async def test_can_add_a_skill_manually(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        python = next(
            s for s in (await client.get(SKILLS)).json() if s["canonical_name"] == "Python"
        )

        response = await client.post(
            f"{SKILLS}/me", headers=headers, json={"skill_id": python["id"], "proficiency": 4}
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "confirmed"
        assert body["source"] == "manual"
        assert body["proficiency"] == 4

    async def test_manual_skill_appears_as_confirmed(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        skill_id = (await client.get(SKILLS)).json()[0]["id"]
        await client.post(f"{SKILLS}/me", headers=headers, json={"skill_id": skill_id})

        profile = (await client.get(f"{SKILLS}/me", headers=headers)).json()
        assert profile["total_confirmed"] == 1

    async def test_unknown_skill_is_404(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        response = await client.post(
            f"{SKILLS}/me", headers=headers, json={"skill_id": str(uuid.uuid4())}
        )
        assert response.status_code == 404

    async def test_can_reject_a_skill(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        skill_id = (await client.get(SKILLS)).json()[0]["id"]
        await client.post(f"{SKILLS}/me", headers=headers, json={"skill_id": skill_id})

        response = await client.patch(
            f"{SKILLS}/me/{skill_id}", headers=headers, json={"status": "rejected"}
        )
        assert response.status_code == 200

        # Rejected entries are tombstones — kept in the database, hidden from the profile.
        profile = (await client.get(f"{SKILLS}/me", headers=headers)).json()
        assert profile["total_confirmed"] == 0
        assert profile["total_suggested"] == 0

    async def test_updating_a_skill_not_in_the_profile_is_404(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        skill_id = (await client.get(SKILLS)).json()[0]["id"]

        response = await client.patch(
            f"{SKILLS}/me/{skill_id}", headers=headers, json={"status": "confirmed"}
        )
        assert response.status_code == 404

    async def test_profiles_are_private(self, client: AsyncClient) -> None:
        alice = await register_and_login(client)
        bob = await register_and_login(client)
        skill_id = (await client.get(SKILLS)).json()[0]["id"]
        await client.post(f"{SKILLS}/me", headers=alice, json={"skill_id": skill_id})

        assert (await client.get(f"{SKILLS}/me", headers=bob)).json()["total_confirmed"] == 0


class TestJobCreation:
    async def test_extracts_skills_from_the_description(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)

        response = await client.post(
            JOBS,
            headers=headers,
            json={"title": "Backend Engineer", "description": JOB_DESCRIPTION},
        )

        assert response.status_code == 201, response.text
        found = {s["skill"]["canonical_name"] for s in response.json()["required_skills"]}
        for expected in ("Python", "FastAPI", "PostgreSQL", "Redis", "Docker", "AWS"):
            assert expected in found

    async def test_repeated_skills_score_higher_importance(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        body = (
            await client.post(
                JOBS,
                headers=headers,
                json={"title": "Backend Engineer", "description": JOB_DESCRIPTION},
            )
        ).json()

        by_name = {s["skill"]["canonical_name"]: s["importance"] for s in body["required_skills"]}
        # "Docker" appears five times, "Kubernetes" once.
        assert by_name["Docker"] > by_name["Kubernetes"]

    async def test_title_contributes_skills(self, client: AsyncClient) -> None:
        # A title like "Senior Kubernetes Engineer" may name the key skill exactly once.
        headers = await register_and_login(client)
        body = (
            await client.post(
                JOBS,
                headers=headers,
                json={
                    "title": "Senior Rust Engineer",
                    "description": (
                        "A role building high performance systems for our platform team."
                    ),
                },
            )
        ).json()

        assert "Rust" in {s["skill"]["canonical_name"] for s in body["required_skills"]}

    async def test_short_descriptions_are_rejected(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        response = await client.post(
            JOBS, headers=headers, json={"title": "Engineer", "description": "too short"}
        )
        assert response.status_code == 422

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            JOBS, json={"title": "Engineer", "description": JOB_DESCRIPTION}
        )
        assert response.status_code == 401


class TestRecruiterRole:
    async def test_job_seeker_cannot_publish_a_public_posting(self, client: AsyncClient) -> None:
        headers = await register_and_login(client, role="job_seeker")

        response = await client.post(
            JOBS,
            headers=headers,
            json={"title": "Backend Engineer", "description": JOB_DESCRIPTION, "is_public": True},
        )

        assert response.status_code == 403

    async def test_recruiter_can_publish(self, client: AsyncClient) -> None:
        headers = await register_and_login(client, role="recruiter")

        response = await client.post(
            JOBS,
            headers=headers,
            json={"title": "Backend Engineer", "description": JOB_DESCRIPTION, "is_public": True},
        )

        assert response.status_code == 201
        assert response.json()["is_public"] is True

    async def test_job_seeker_can_still_create_private_jobs(self, client: AsyncClient) -> None:
        headers = await register_and_login(client, role="job_seeker")
        response = await client.post(
            JOBS,
            headers=headers,
            json={"title": "Target Role", "description": JOB_DESCRIPTION, "is_public": False},
        )
        assert response.status_code == 201


class TestJobVisibility:
    async def test_public_postings_are_visible_to_everyone(self, client: AsyncClient) -> None:
        recruiter = await register_and_login(client, role="recruiter")
        seeker = await register_and_login(client)
        job_id = (
            await client.post(
                JOBS,
                headers=recruiter,
                json={"title": "Public Role", "description": JOB_DESCRIPTION, "is_public": True},
            )
        ).json()["id"]

        assert (await client.get(f"{JOBS}/{job_id}", headers=seeker)).status_code == 200

    async def test_private_jobs_are_404_for_others(self, client: AsyncClient) -> None:
        alice = await register_and_login(client)
        bob = await register_and_login(client)
        job_id = (
            await client.post(
                JOBS,
                headers=alice,
                json={"title": "Private Target", "description": JOB_DESCRIPTION},
            )
        ).json()["id"]

        # 404, not 403 — a 403 would confirm the id exists.
        assert (await client.get(f"{JOBS}/{job_id}", headers=bob)).status_code == 404

    async def test_list_shows_own_and_public_only(self, client: AsyncClient) -> None:
        recruiter = await register_and_login(client, role="recruiter")
        seeker = await register_and_login(client)

        await client.post(
            JOBS,
            headers=recruiter,
            json={"title": "Public", "description": JOB_DESCRIPTION, "is_public": True},
        )
        await client.post(
            JOBS,
            headers=recruiter,
            json={"title": "Recruiter Private", "description": JOB_DESCRIPTION},
        )
        await client.post(
            JOBS, headers=seeker, json={"title": "Seeker Private", "description": JOB_DESCRIPTION}
        )

        titles = {j["title"] for j in (await client.get(JOBS, headers=seeker)).json()}
        assert titles == {"Public", "Seeker Private"}


class TestJobModification:
    async def test_owner_can_edit(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        job_id = (
            await client.post(
                JOBS, headers=headers, json={"title": "Old", "description": JOB_DESCRIPTION}
            )
        ).json()["id"]

        response = await client.patch(f"{JOBS}/{job_id}", headers=headers, json={"title": "New"})
        assert response.status_code == 200
        assert response.json()["title"] == "New"

    async def test_editing_the_description_re_extracts_skills(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        job_id = (
            await client.post(
                JOBS, headers=headers, json={"title": "Role", "description": JOB_DESCRIPTION}
            )
        ).json()["id"]

        updated = (
            await client.patch(
                f"{JOBS}/{job_id}",
                headers=headers,
                json={
                    "description": (
                        "A frontend role building interfaces with React and TypeScript, "
                        "styled using Tailwind CSS across our product surface."
                    )
                },
            )
        ).json()

        found = {s["skill"]["canonical_name"] for s in updated["required_skills"]}
        assert "React" in found
        assert "Docker" not in found  # stale skills are gone

    async def test_non_owner_cannot_edit_a_public_posting(self, client: AsyncClient) -> None:
        recruiter = await register_and_login(client, role="recruiter")
        seeker = await register_and_login(client)
        job_id = (
            await client.post(
                JOBS,
                headers=recruiter,
                json={"title": "Public", "description": JOB_DESCRIPTION, "is_public": True},
            )
        ).json()["id"]

        # Visible does not mean writable.
        assert (
            await client.patch(f"{JOBS}/{job_id}", headers=seeker, json={"title": "Hijacked"})
        ).status_code == 404

    async def test_owner_can_delete(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        job_id = (
            await client.post(
                JOBS, headers=headers, json={"title": "Temp", "description": JOB_DESCRIPTION}
            )
        ).json()["id"]

        assert (await client.delete(f"{JOBS}/{job_id}", headers=headers)).status_code == 204
        assert (await client.get(f"{JOBS}/{job_id}", headers=headers)).status_code == 404


class TestUploadStillWorks:
    async def test_resume_upload_is_unaffected(self, client: AsyncClient) -> None:
        headers = await register_and_login(client)
        files = {"file": ("ada.pdf", make_pdf("Python"), PDF_CONTENT_TYPE)}

        assert (
            await client.post("/api/v1/resumes", headers=headers, files=files)
        ).status_code == 202
