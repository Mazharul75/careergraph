"""Resume upload through the real HTTP stack and a real database.

The queue is stubbed out with a recording dispatcher. That is deliberate: these tests are
about the *request* path — routing, multipart parsing, authentication, ownership, status codes
— not about whether Celery works. Requiring a live broker here would make the suite slow,
flaky, and impossible to run offline.

The task itself is exercised separately, for real, in test_parse_task.py.
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
from app.services.extraction import DOCX_CONTENT_TYPE, PDF_CONTENT_TYPE
from tests.unit.test_extraction import make_docx, make_pdf

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery-staple"
AUTH = "/api/v1/auth"
RESUMES = "/api/v1/resumes"


class RecordingDispatcher:
    def __init__(self) -> None:
        self.enqueued: list[uuid.UUID] = []

    def enqueue_resume_parse(self, resume_id: uuid.UUID) -> None:
        self.enqueued.append(resume_id)


@pytest.fixture
def dispatcher() -> RecordingDispatcher:
    return RecordingDispatcher()


@pytest.fixture
async def app(db_session: AsyncSession, dispatcher: RecordingDispatcher) -> FastAPI:
    application = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    application.dependency_overrides[get_db] = _override_get_db
    application.dependency_overrides[get_task_dispatcher] = lambda: dispatcher
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    email = f"resume-{uuid.uuid4().hex[:8]}@example.com"
    await client.post(f"{AUTH}/register", json={"email": email, "password": PASSWORD})
    tokens = (
        await client.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    ).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def pdf_upload(name: str = "ada.pdf", text: str = "Python and PostgreSQL") -> dict:
    return {"file": (name, make_pdf(text), PDF_CONTENT_TYPE)}


class TestUploadEndpoint:
    async def test_returns_202_accepted(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.post(RESUMES, headers=auth_headers, files=pdf_upload())

        # 202, not 201: the row exists, but the thing the client wants — parsed text — does
        # not yet. The status code is the contract that tells them to poll.
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["status"] == "pending"
        assert body["original_filename"] == "ada.pdf"
        assert body["size_bytes"] > 0

    async def test_enqueues_exactly_one_task(
        self, client: AsyncClient, auth_headers: dict[str, str], dispatcher: RecordingDispatcher
    ) -> None:
        response = await client.post(RESUMES, headers=auth_headers, files=pdf_upload())

        assert dispatcher.enqueued == [uuid.UUID(response.json()["id"])]

    async def test_response_never_contains_the_file_bytes(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        # ResumeSummary has no file_data field, so this asserts the schema boundary holds.
        response = await client.post(RESUMES, headers=auth_headers, files=pdf_upload())

        assert "file_data" not in response.json()
        assert "%PDF" not in response.text

    async def test_accepts_docx(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        files = {"file": ("ada.docx", make_docx(["Python"]), DOCX_CONTENT_TYPE)}
        response = await client.post(RESUMES, headers=auth_headers, files=files)

        assert response.status_code == 202

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.post(RESUMES, files=pdf_upload())).status_code == 401


class TestUploadValidation:
    async def test_rejects_an_empty_file(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        files = {"file": ("empty.pdf", b"", PDF_CONTENT_TYPE)}
        assert (await client.post(RESUMES, headers=auth_headers, files=files)).status_code == 400

    async def test_rejects_a_disallowed_content_type(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        files = {"file": ("notes.txt", b"just some text", "text/plain")}
        assert (await client.post(RESUMES, headers=auth_headers, files=files)).status_code == 400

    async def test_rejects_bytes_that_contradict_the_content_type(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        # An executable renamed to .pdf and declared as application/pdf. Magic-byte detection
        # is the only check here the client cannot simply lie its way past.
        files = {"file": ("payload.pdf", b"MZ\x90\x00executable", PDF_CONTENT_TYPE)}
        response = await client.post(RESUMES, headers=auth_headers, files=files)

        assert response.status_code == 400
        assert "PDF or DOCX" in response.json()["detail"]

    async def test_rejects_an_oversized_file(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        oversized = b"%PDF-" + b"x" * (5 * 1024 * 1024)
        files = {"file": ("big.pdf", oversized, PDF_CONTENT_TYPE)}
        response = await client.post(RESUMES, headers=auth_headers, files=files)

        # 413, not 400: the request shape is fine, the payload is simply too large.
        assert response.status_code == 413

    async def test_missing_file_field_is_422(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        assert (await client.post(RESUMES, headers=auth_headers)).status_code == 422


class TestStatusPolling:
    async def test_get_returns_current_status(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resume_id = (await client.post(RESUMES, headers=auth_headers, files=pdf_upload())).json()[
            "id"
        ]

        response = await client.get(f"{RESUMES}/{resume_id}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    async def test_list_returns_only_your_resumes(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await client.post(RESUMES, headers=auth_headers, files=pdf_upload("mine.pdf"))

        other_email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        await client.post(f"{AUTH}/register", json={"email": other_email, "password": PASSWORD})
        other_tokens = (
            await client.post(f"{AUTH}/login", json={"email": other_email, "password": PASSWORD})
        ).json()
        other_headers = {"Authorization": f"Bearer {other_tokens['access_token']}"}
        await client.post(RESUMES, headers=other_headers, files=pdf_upload("theirs.pdf"))

        mine = (await client.get(RESUMES, headers=auth_headers)).json()

        assert [r["original_filename"] for r in mine] == ["mine.pdf"]

    async def test_another_users_resume_is_404_not_403(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resume_id = (await client.post(RESUMES, headers=auth_headers, files=pdf_upload())).json()[
            "id"
        ]

        other_email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        await client.post(f"{AUTH}/register", json={"email": other_email, "password": PASSWORD})
        other_tokens = (
            await client.post(f"{AUTH}/login", json={"email": other_email, "password": PASSWORD})
        ).json()

        response = await client.get(
            f"{RESUMES}/{resume_id}",
            headers={"Authorization": f"Bearer {other_tokens['access_token']}"},
        )

        # 404, not 403 — a 403 would confirm that this id exists, letting anyone enumerate
        # how many resumes the system holds.
        assert response.status_code == 404

    async def test_unknown_id_is_404(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(f"{RESUMES}/{uuid.uuid4()}", headers=auth_headers)
        assert response.status_code == 404

    async def test_text_endpoint_is_null_until_parsing_completes(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        resume_id = (await client.post(RESUMES, headers=auth_headers, files=pdf_upload())).json()[
            "id"
        ]

        body = (await client.get(f"{RESUMES}/{resume_id}/text", headers=auth_headers)).json()

        assert body["status"] == "pending"
        assert body["extracted_text"] is None
        assert body["character_count"] == 0


class TestQueueFairness:
    async def test_one_account_cannot_monopolise_the_worker(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        for _ in range(3):
            response = await client.post(RESUMES, headers=auth_headers, files=pdf_upload())
            assert response.status_code == 202

        fourth = await client.post(RESUMES, headers=auth_headers, files=pdf_upload())
        assert fourth.status_code == 409


class TestOpenApiSurface:
    async def test_resume_routes_are_documented(self, client: AsyncClient) -> None:
        paths = (await client.get("/openapi.json")).json()["paths"]

        assert RESUMES in paths
        assert f"{RESUMES}/{{resume_id}}" in paths
        assert f"{RESUMES}/{{resume_id}}/text" in paths
