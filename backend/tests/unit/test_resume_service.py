"""ResumeService against in-memory fakes and a recording dispatcher.

No database, no Redis, no Celery import. The `TaskDispatcher` protocol is what makes this
possible: the service asks for "something that can enqueue a parse", and a test hands it a
list.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.resume import ParseStatus, Resume
from app.services.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    ResumeNotFoundError,
    TooManyPendingResumesError,
    UnsupportedFileTypeError,
)
from app.services.extraction import DOCX_CONTENT_TYPE, PDF_CONTENT_TYPE, ExtractionError
from app.services.resume import MAX_PENDING_PER_USER, ResumeService
from tests.unit.test_extraction import make_docx, make_pdf

MAX_BYTES = 5 * 1024 * 1024


class FakeResumeRepository:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, Resume] = {}

    async def get_for_user(self, resume_id: uuid.UUID, user_id: uuid.UUID) -> Resume | None:
        resume = self.rows.get(resume_id)
        # Mirrors the real query's WHERE clause: ownership is part of the lookup, not a
        # separate check a caller could forget.
        return resume if resume and resume.user_id == user_id else None

    async def get_with_text(self, resume_id: uuid.UUID, user_id: uuid.UUID) -> Resume | None:
        return await self.get_for_user(resume_id, user_id)

    async def list_for_user(self, user_id: uuid.UUID, *, limit: int = 50) -> list[Resume]:
        return [r for r in self.rows.values() if r.user_id == user_id][:limit]

    async def count_pending_for_user(self, user_id: uuid.UUID) -> int:
        return sum(
            1
            for r in self.rows.values()
            if r.user_id == user_id and r.status in (ParseStatus.PENDING, ParseStatus.PROCESSING)
        )

    def add(self, entity: Resume) -> Resume:
        if entity.id is None:
            entity.id = uuid.uuid4()
        self.rows[entity.id] = entity
        return entity


class RecordingDispatcher:
    def __init__(self) -> None:
        self.enqueued: list[uuid.UUID] = []

    def enqueue_resume_parse(self, resume_id: uuid.UUID) -> None:
        self.enqueued.append(resume_id)


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def flush(self) -> None:
        pass


@pytest.fixture
def repo() -> FakeResumeRepository:
    return FakeResumeRepository()


@pytest.fixture
def dispatcher() -> RecordingDispatcher:
    return RecordingDispatcher()


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def service(
    repo: FakeResumeRepository, dispatcher: RecordingDispatcher, uow: FakeUnitOfWork
) -> ResumeService:
    return ResumeService(resumes=repo, dispatcher=dispatcher, uow=uow, max_upload_bytes=MAX_BYTES)


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


class TestUpload:
    async def test_accepts_a_pdf_and_queues_it(
        self, service: ResumeService, dispatcher: RecordingDispatcher, user_id: uuid.UUID
    ) -> None:
        resume = await service.upload(
            user_id=user_id,
            filename="ada.pdf",
            content_type=PDF_CONTENT_TYPE,
            data=make_pdf("Python"),
        )

        assert resume.status is ParseStatus.PENDING
        assert dispatcher.enqueued == [resume.id]

    async def test_accepts_a_docx(self, service: ResumeService, user_id: uuid.UUID) -> None:
        resume = await service.upload(
            user_id=user_id,
            filename="ada.docx",
            content_type=DOCX_CONTENT_TYPE,
            data=make_docx(["Python"]),
        )
        assert resume.status is ParseStatus.PENDING

    async def test_does_not_parse_inline(self, service: ResumeService, user_id: uuid.UUID) -> None:
        # The whole point of the queue: upload returns before any parsing has happened.
        resume = await service.upload(
            user_id=user_id,
            filename="ada.pdf",
            content_type=PDF_CONTENT_TYPE,
            data=make_pdf("Python"),
        )
        assert resume.extracted_text is None

    async def test_commits_before_enqueuing(
        self, service: ResumeService, uow: FakeUnitOfWork, user_id: uuid.UUID
    ) -> None:
        # If the message were published first, a fast worker could query for a row that has not
        # been committed — an intermittent "resume no longer exists" under load.
        await service.upload(
            user_id=user_id,
            filename="a.pdf",
            content_type=PDF_CONTENT_TYPE,
            data=make_pdf("x"),
        )
        assert uow.commits >= 1

    async def test_rejects_an_empty_file(self, service: ResumeService, user_id: uuid.UUID) -> None:
        with pytest.raises(EmptyFileError):
            await service.upload(
                user_id=user_id, filename="a.pdf", content_type=PDF_CONTENT_TYPE, data=b""
            )

    async def test_rejects_an_oversized_file(
        self, service: ResumeService, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(FileTooLargeError):
            await service.upload(
                user_id=user_id,
                filename="a.pdf",
                content_type=PDF_CONTENT_TYPE,
                data=b"%PDF-" + b"x" * MAX_BYTES,
            )

    async def test_rejects_a_disallowed_content_type(
        self, service: ResumeService, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(UnsupportedFileTypeError):
            await service.upload(
                user_id=user_id,
                filename="a.txt",
                content_type="text/plain",
                data=make_pdf("x"),
            )

    async def test_rejects_bytes_that_contradict_the_declared_type(
        self, service: ResumeService, user_id: uuid.UUID
    ) -> None:
        # Declaring application/pdf does not make an executable a PDF. This is the check that
        # matters, because Content-Type is entirely under the client's control.
        with pytest.raises(ExtractionError):
            await service.upload(
                user_id=user_id,
                filename="payload.pdf",
                content_type=PDF_CONTENT_TYPE,
                data=b"MZ\x90\x00" + b"windows executable",
            )

    async def test_nothing_is_queued_when_validation_fails(
        self, service: ResumeService, dispatcher: RecordingDispatcher, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(EmptyFileError):
            await service.upload(
                user_id=user_id, filename="a.pdf", content_type=PDF_CONTENT_TYPE, data=b""
            )
        assert dispatcher.enqueued == []

    async def test_caps_concurrent_pending_uploads(
        self, service: ResumeService, user_id: uuid.UUID
    ) -> None:
        # One account must not be able to monopolise a single shared worker.
        for _ in range(MAX_PENDING_PER_USER):
            await service.upload(
                user_id=user_id,
                filename="a.pdf",
                content_type=PDF_CONTENT_TYPE,
                data=make_pdf("x"),
            )

        with pytest.raises(TooManyPendingResumesError):
            await service.upload(
                user_id=user_id,
                filename="a.pdf",
                content_type=PDF_CONTENT_TYPE,
                data=make_pdf("x"),
            )

    async def test_the_cap_is_per_user(self, service: ResumeService, user_id: uuid.UUID) -> None:
        for _ in range(MAX_PENDING_PER_USER):
            await service.upload(
                user_id=user_id,
                filename="a.pdf",
                content_type=PDF_CONTENT_TYPE,
                data=make_pdf("x"),
            )

        # A different account is unaffected by this one's backlog.
        other = await service.upload(
            user_id=uuid.uuid4(),
            filename="b.pdf",
            content_type=PDF_CONTENT_TYPE,
            data=make_pdf("x"),
        )
        assert other.status is ParseStatus.PENDING


class TestFilenameSanitisation:
    @pytest.mark.parametrize(
        ("supplied", "expected"),
        [
            ("../../etc/passwd", "passwd"),
            ("C:\\Users\\ada\\resume.pdf", "resume.pdf"),
            ("normal.pdf", "normal.pdf"),
            ("", "resume"),
        ],
    )
    async def test_strips_path_components(
        self, service: ResumeService, user_id: uuid.UUID, supplied: str, expected: str
    ) -> None:
        # The name is never used as a filesystem path — bytes go to Postgres — but it is echoed
        # back in API responses and rendered in the UI.
        resume = await service.upload(
            user_id=user_id,
            filename=supplied,
            content_type=PDF_CONTENT_TYPE,
            data=make_pdf("x"),
        )
        assert resume.original_filename == expected

    async def test_truncates_absurdly_long_names(
        self, service: ResumeService, user_id: uuid.UUID
    ) -> None:
        resume = await service.upload(
            user_id=user_id,
            filename="a" * 500 + ".pdf",
            content_type=PDF_CONTENT_TYPE,
            data=make_pdf("x"),
        )
        assert len(resume.original_filename) <= 255


class TestOwnership:
    async def test_a_user_can_read_their_own_resume(
        self, service: ResumeService, user_id: uuid.UUID
    ) -> None:
        uploaded = await service.upload(
            user_id=user_id,
            filename="a.pdf",
            content_type=PDF_CONTENT_TYPE,
            data=make_pdf("x"),
        )
        assert (await service.get(resume_id=uploaded.id, user_id=user_id)).id == uploaded.id

    async def test_another_users_resume_is_not_found(
        self, service: ResumeService, user_id: uuid.UUID
    ) -> None:
        # Not "forbidden" — that would confirm the id exists.
        uploaded = await service.upload(
            user_id=user_id,
            filename="a.pdf",
            content_type=PDF_CONTENT_TYPE,
            data=make_pdf("x"),
        )
        with pytest.raises(ResumeNotFoundError):
            await service.get(resume_id=uploaded.id, user_id=uuid.uuid4())

    async def test_unknown_id_raises_the_same_error(
        self, service: ResumeService, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ResumeNotFoundError):
            await service.get(resume_id=uuid.uuid4(), user_id=user_id)

    async def test_listing_only_returns_your_own(
        self, service: ResumeService, user_id: uuid.UUID
    ) -> None:
        await service.upload(
            user_id=user_id,
            filename="mine.pdf",
            content_type=PDF_CONTENT_TYPE,
            data=make_pdf("x"),
        )
        await service.upload(
            user_id=uuid.uuid4(),
            filename="theirs.pdf",
            content_type=PDF_CONTENT_TYPE,
            data=make_pdf("x"),
        )

        mine = await service.list_for_user(user_id=user_id)
        assert [r.original_filename for r in mine] == ["mine.pdf"]
