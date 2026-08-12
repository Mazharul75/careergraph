"""The Celery task, executed for real against the database.

These are plain synchronous tests, and they call ``parse_resume(...)`` directly rather than
through ``.delay()``. That runs the actual task body — including the synchronous worker session
from ADR-0005 — without needing a broker or a running worker. Going through Celery would test
Celery; this tests our code.

Because the worker session commits outside the async suite's rollback fixture, each test owns
its rows and deletes them in teardown.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from app.core.security import hash_password
from app.db.sync_session import SyncSessionFactory
from app.models.resume import ParseStatus, Resume
from app.models.user import User
from app.workers.tasks import parse_resume
from tests.unit.test_extraction import make_docx, make_pdf

pytestmark = pytest.mark.integration


@pytest.fixture
def owner() -> Iterator[uuid.UUID]:
    """A committed user row, removed afterwards.

    Resumes cascade on delete, so removing the user cleans up everything a test created.
    """
    session = SyncSessionFactory()
    user = User(
        email=f"worker-{uuid.uuid4().hex[:10]}@example.com",
        password_hash=hash_password("correct-horse-battery-staple"),
        full_name="Worker Test",
    )
    session.add(user)
    session.commit()
    user_id = user.id
    session.close()

    yield user_id

    cleanup = SyncSessionFactory()
    cleanup.query(User).filter(User.id == user_id).delete()
    cleanup.commit()
    cleanup.close()


def create_resume(user_id: uuid.UUID, data: bytes, filename: str = "ada.pdf") -> uuid.UUID:
    session = SyncSessionFactory()
    resume = Resume(
        user_id=user_id,
        original_filename=filename,
        content_type="application/pdf",
        size_bytes=len(data),
        file_data=data,
        status=ParseStatus.PENDING,
    )
    session.add(resume)
    session.commit()
    resume_id = resume.id
    session.close()
    return resume_id


def reload_resume(resume_id: uuid.UUID) -> Resume:
    session = SyncSessionFactory()
    try:
        resume = session.get(Resume, resume_id)
        assert resume is not None
        # Touch the deferred columns while the session is open, so assertions after close()
        # do not trigger a lazy load on a detached instance.
        _ = resume.extracted_text, resume.file_data
        return resume
    finally:
        session.close()


class TestSuccessfulParse:
    def test_extracts_text_and_marks_complete(self, owner: uuid.UUID) -> None:
        resume_id = create_resume(owner, make_pdf("Python and PostgreSQL"))

        result = parse_resume(str(resume_id))

        assert result == "complete"
        resume = reload_resume(resume_id)
        assert resume.status is ParseStatus.COMPLETE
        assert resume.extracted_text is not None
        assert "Python" in resume.extracted_text
        assert resume.error_message is None

    def test_discards_the_uploaded_bytes_afterwards(self, owner: uuid.UUID) -> None:
        # The text is what downstream phases need; the original document is not. Dropping it
        # keeps the free-tier database small and means a database compromise exposes far less
        # than the resumes users handed us.
        resume_id = create_resume(owner, make_pdf("Python"))

        parse_resume(str(resume_id))

        assert reload_resume(resume_id).file_data is None

    def test_parses_docx_too(self, owner: uuid.UUID) -> None:
        resume_id = create_resume(owner, make_docx(["Ada Lovelace", "Redis"]), "ada.docx")

        parse_resume(str(resume_id))

        resume = reload_resume(resume_id)
        assert resume.status is ParseStatus.COMPLETE
        assert "Redis" in (resume.extracted_text or "")


class TestFailureHandling:
    def test_corrupt_document_fails_terminally(self, owner: uuid.UUID) -> None:
        # A malformed file will fail identically on every retry, so retrying is pointless.
        resume_id = create_resume(owner, b"%PDF-1.4\nnot really a pdf")

        result = parse_resume(str(resume_id))

        assert result == "failed"
        resume = reload_resume(resume_id)
        assert resume.status is ParseStatus.FAILED
        assert resume.error_message
        assert resume.file_data is None  # unusable bytes are not kept

    def test_error_message_is_safe_to_display(self, owner: uuid.UUID) -> None:
        resume_id = create_resume(owner, b"%PDF-1.4\ncorrupt")

        parse_resume(str(resume_id))

        message = reload_resume(resume_id).error_message or ""
        assert "Traceback" not in message
        assert "/app" not in message
        assert len(message) <= 500  # fits the column

    def test_missing_resume_is_not_an_error(self, owner: uuid.UUID) -> None:
        # The user deleted it between enqueue and execution. Raising here would make Celery
        # retry forever against a row that will never come back.
        assert parse_resume(str(uuid.uuid4())) == "missing"


class TestIdempotency:
    def test_running_twice_is_harmless(self, owner: uuid.UUID) -> None:
        """`task_acks_late` means a worker that dies mid-parse gets the message redelivered.

        The second run must not corrupt a good result — which is what makes at-least-once
        delivery safe to rely on.
        """
        resume_id = create_resume(owner, make_pdf("Python"))

        assert parse_resume(str(resume_id)) == "complete"
        first_text = reload_resume(resume_id).extracted_text

        assert parse_resume(str(resume_id)) == "already-complete"

        resume = reload_resume(resume_id)
        assert resume.status is ParseStatus.COMPLETE
        assert resume.extracted_text == first_text

    def test_a_resume_with_no_bytes_fails_rather_than_crashing(self, owner: uuid.UUID) -> None:
        resume_id = create_resume(owner, make_pdf("Python"))
        parse_resume(str(resume_id))  # clears file_data

        session = SyncSessionFactory()
        resume = session.get(Resume, resume_id)
        assert resume is not None
        resume.status = ParseStatus.PENDING  # simulate a stale requeue
        session.commit()
        session.close()

        assert parse_resume(str(resume_id)) == "no-data"
        assert reload_resume(resume_id).status is ParseStatus.FAILED
