"""The maintenance sweepers, executed for real against the database.

Same pattern as ``test_parse_task.py``: the task functions are called directly (no broker),
and because the worker session commits for real, each test cleans up through the user row's
delete cascade.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.core.security import hash_password
from app.db.sync_session import SyncSessionFactory
from app.models.refresh_token import RefreshToken
from app.models.resume import ParseStatus, Resume
from app.models.user import User
from app.workers import maintenance
from app.workers.maintenance import purge_expired_refresh_tokens, requeue_stuck_resumes

pytestmark = pytest.mark.integration


@pytest.fixture
def owner() -> Iterator[uuid.UUID]:
    session = SyncSessionFactory()
    user = User(
        email=f"sweeper-{uuid.uuid4().hex[:10]}@example.com",
        password_hash=hash_password("correct-horse-battery-staple"),
        full_name="Sweeper Test",
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


def _make_token(user_id: uuid.UUID, *, expires_in_days: int) -> uuid.UUID:
    session = SyncSessionFactory()
    token = RefreshToken(
        user_id=user_id,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,  # 64 hex chars, unique
        family_id=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
    )
    session.add(token)
    session.commit()
    token_id = token.id
    session.close()
    return token_id


def _make_resume(
    user_id: uuid.UUID,
    *,
    status: ParseStatus,
    age_minutes: int,
    file_data: bytes | None,
) -> uuid.UUID:
    session = SyncSessionFactory()
    resume = Resume(
        user_id=user_id,
        original_filename="stuck.pdf",
        content_type="application/pdf",
        # The check constraint demands a positive size; a row whose bytes were already
        # cleared still remembers how big the original upload was.
        size_bytes=len(file_data) if file_data else 1024,
        file_data=file_data,
        status=status,
        # Explicit value on insert wins over the column's server_default, which is what lets
        # a test manufacture a row that looks `age_minutes` old.
        updated_at=datetime.now(UTC) - timedelta(minutes=age_minutes),
    )
    session.add(resume)
    session.commit()
    resume_id = resume.id
    session.close()
    return resume_id


def _get_resume(resume_id: uuid.UUID) -> Resume | None:
    session = SyncSessionFactory()
    resume = session.get(Resume, resume_id)
    session.close()
    return resume


class TestPurgeExpiredRefreshTokens:
    def test_removes_expired_and_keeps_live(self, owner: uuid.UUID) -> None:
        expired_id = _make_token(owner, expires_in_days=-1)
        live_id = _make_token(owner, expires_in_days=10)

        purge_expired_refresh_tokens()

        session = SyncSessionFactory()
        assert session.get(RefreshToken, expired_id) is None
        assert session.get(RefreshToken, live_id) is not None
        session.close()

    def test_spent_but_unexpired_tokens_survive(self, owner: uuid.UUID) -> None:
        """Revoked-but-unexpired rows are the reuse-detection tripwire — never purged."""
        spent_id = _make_token(owner, expires_in_days=10)
        session = SyncSessionFactory()
        token = session.get(RefreshToken, spent_id)
        assert token is not None
        token.revoked_at = datetime.now(UTC)
        session.commit()
        session.close()

        purge_expired_refresh_tokens()

        session = SyncSessionFactory()
        assert session.get(RefreshToken, spent_id) is not None
        session.close()


class TestRequeueStuckResumes:
    @pytest.fixture
    def enqueued(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        """Capture what the sweeper enqueues instead of touching a real broker."""
        calls: list[str] = []

        class _FakeTask:
            @staticmethod
            def delay(resume_id: str, **_kwargs: Any) -> None:
                calls.append(resume_id)

        monkeypatch.setattr(maintenance, "parse_resume", _FakeTask)
        return calls

    def test_requeues_old_pending_with_data(self, owner: uuid.UUID, enqueued: list[str]) -> None:
        stuck_id = _make_resume(owner, status=ParseStatus.PENDING, age_minutes=60, file_data=b"x")

        count = requeue_stuck_resumes()

        assert count == 1
        assert enqueued == [str(stuck_id)]
        resume = _get_resume(stuck_id)
        assert resume is not None
        assert resume.status is ParseStatus.PENDING  # the re-run parse will advance it

    def test_requeues_a_resume_stranded_mid_parse(
        self, owner: uuid.UUID, enqueued: list[str]
    ) -> None:
        """A worker killed mid-parse leaves `processing`, not `pending`.

        This is the real production failure: the task set the status, committed, and the
        process was then killed loading the embedding model. Redis will not redeliver the
        message until its visibility timeout elapses, so the sweeper is what rescues it.
        """
        stranded = _make_resume(
            owner, status=ParseStatus.PROCESSING, age_minutes=60, file_data=b"x"
        )

        count = requeue_stuck_resumes()

        assert count == 1
        assert enqueued == [str(stranded)]

    def test_ignores_a_parse_that_is_merely_slow(
        self, owner: uuid.UUID, enqueued: list[str]
    ) -> None:
        """The cutoff is far longer than the task's hard time limit, so a running parse is
        never yanked out from under a healthy worker."""
        _make_resume(owner, status=ParseStatus.PROCESSING, age_minutes=2, file_data=b"x")

        assert requeue_stuck_resumes() == 0
        assert enqueued == []

    def test_ignores_fresh_pending(self, owner: uuid.UUID, enqueued: list[str]) -> None:
        _make_resume(owner, status=ParseStatus.PENDING, age_minutes=1, file_data=b"x")

        assert requeue_stuck_resumes() == 0
        assert enqueued == []

    def test_ignores_terminal_states(self, owner: uuid.UUID, enqueued: list[str]) -> None:
        _make_resume(owner, status=ParseStatus.COMPLETE, age_minutes=60, file_data=None)
        _make_resume(owner, status=ParseStatus.FAILED, age_minutes=60, file_data=None)

        assert requeue_stuck_resumes() == 0
        assert enqueued == []

    def test_fails_stuck_resume_whose_bytes_are_gone(
        self, owner: uuid.UUID, enqueued: list[str]
    ) -> None:
        gone_id = _make_resume(owner, status=ParseStatus.PENDING, age_minutes=60, file_data=None)

        count = requeue_stuck_resumes()

        assert count == 0
        assert enqueued == []
        resume = _get_resume(gone_id)
        assert resume is not None
        assert resume.status is ParseStatus.FAILED
        assert resume.error_message is not None
        assert "upload it again" in resume.error_message


class TestEmbeddingResilience:
    """The OOM-kill lessons from production (2026-08-20), locked in as tests."""

    def test_embed_tasks_do_not_use_acks_late(self) -> None:
        """The fix for the crash loop.

        An OOM kill never runs an ``except`` clause, so with ``acks_late`` the broker
        redelivers the message, the fresh worker loads the same 200 MB model, and is killed
        again -- taking the API sharing its container down every visibility timeout. Losing a
        best-effort vector is the cheaper failure, so these two acknowledge on receipt.
        """
        from app.workers.tasks import embed_job, embed_resume

        assert embed_resume.acks_late is False
        assert embed_job.acks_late is False

    def test_parse_still_uses_acks_late(self) -> None:
        """The counterpart: losing a *parse* would lose real work, so it must be redelivered."""
        from app.workers.tasks import parse_resume

        assert parse_resume.acks_late is not False

    def test_embedding_can_be_switched_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The production kill switch, if memory tuning is still not enough."""
        from app.core.config import get_settings
        from app.services.embedding import EmbeddingDisabledError, embed_texts

        monkeypatch.setenv("EMBEDDING_ENABLED", "false")
        get_settings.cache_clear()
        try:
            with pytest.raises(EmbeddingDisabledError):
                embed_texts(["some resume text"])
        finally:
            get_settings.cache_clear()

    def test_disabled_embedding_is_not_an_error_for_the_task(
        self, monkeypatch: pytest.MonkeyPatch, owner: uuid.UUID
    ) -> None:
        """A switched-off feature must not burn the retry budget or mark anything failed."""
        from app.core.config import get_settings
        from app.workers.tasks import embed_resume

        session = SyncSessionFactory()
        resume = Resume(
            user_id=owner,
            original_filename="ada.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            status=ParseStatus.COMPLETE,
            extracted_text="Python and PostgreSQL and Docker",
        )
        session.add(resume)
        session.commit()
        resume_id = resume.id
        session.close()

        monkeypatch.setenv("EMBEDDING_ENABLED", "false")
        get_settings.cache_clear()
        try:
            assert embed_resume(str(resume_id)) == "disabled"
        finally:
            get_settings.cache_clear()

        # The resume is untouched and still perfectly usable. `embedding` is a deferred
        # column, so it has to be read while the session is still open — touching it after
        # close raises DetachedInstanceError rather than returning None.
        check = SyncSessionFactory()
        try:
            stored = check.get(Resume, resume_id)
            assert stored is not None
            assert stored.status is ParseStatus.COMPLETE
            assert stored.embedding is None
        finally:
            check.close()
