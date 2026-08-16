"""Periodic maintenance tasks, scheduled by Celery beat.

**Celery beat** is Celery's cron: a lightweight scheduler that drops task messages onto the
queue at fixed intervals, where the ordinary worker picks them up like any other task. We run
it embedded in the worker process (the ``-B`` flag) rather than as a separate service — with a
single worker instance there is nothing to coordinate, and a separate beat container would be
one more process on a 512 MB instance for no benefit. The known trade-off: if the app ever
scales to several worker instances, embedded beat would fire every schedule once *per
instance*, so it must then move to its own process.

Both tasks are sweepers: they repair states that normal operation can leave behind but cannot
repair itself.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult

from app.core.config import get_settings
from app.db.sync_session import worker_session
from app.models.refresh_token import RefreshToken
from app.models.resume import ParseStatus, Resume
from app.workers.celery_app import celery_app
from app.workers.tasks import parse_resume

logger = logging.getLogger(__name__)


@celery_app.task(name="maintenance.purge_expired_refresh_tokens")
def purge_expired_refresh_tokens() -> int:
    """Delete refresh-token rows that are past their expiry.

    Spent-but-unexpired rows must stay: presenting one again is how theft is detected, so
    deleting them would blind the reuse check (see the RefreshToken model). But once a token
    is past ``expires_at`` it is rejected as expired before the reuse check ever matters —
    a replay of it can no longer succeed or reveal anything. Keeping such rows forever just
    grows the table by one row per login per user per month, unboundedly.
    """
    with worker_session() as session:
        # The cast narrows Session.execute's general Result type to the cursor-backed result
        # a DELETE actually produces — the only kind that carries a meaningful rowcount.
        statement = delete(RefreshToken).where(RefreshToken.expires_at < datetime.now(UTC))
        result = cast("CursorResult[Any]", session.execute(statement))
        purged = result.rowcount

    if purged:
        logger.info("purge_expired_refresh_tokens: removed %d expired tokens", purged)
    return purged


@celery_app.task(name="maintenance.requeue_stuck_resumes")
def requeue_stuck_resumes() -> int:
    """Re-enqueue resumes stranded in a non-terminal state.

    Two distinct failures leave a resume that no amount of waiting will fix, and the UI polls
    forever for both:

    * **``pending``** — the upload endpoint commits the resume row and *then* enqueues the
      parse task. A crash between those two steps loses the message; the row is never picked
      up. This is the one gap in the outbox-less dispatch design (see the dispatcher).
    * **``processing``** — the worker took the job, set the status, and was killed mid-parse
      (an out-of-memory kill on a small instance does exactly this). Redis-backed Celery does
      not redeliver such a message until its visibility timeout elapses, and the row is
      already past ``pending``, so an earlier version of this sweeper walked straight past it.

    Both are repaired the same way, because ``parse_resume`` is idempotent: a resume that
    finished after all sees ``complete`` and exits, and one that genuinely died starts over
    from its still-intact bytes. The cutoff is far longer than the task's hard time limit, so
    a parse that is merely slow is never interrupted.

    A stranded row whose file bytes are already gone cannot be reparsed, so it is failed
    outright with a message that tells the user what to do.
    """
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.stuck_resume_after_minutes)

    with worker_session() as session:
        stuck = (
            session.execute(
                select(Resume.id, Resume.file_data.is_(None)).where(
                    Resume.status.in_([ParseStatus.PENDING, ParseStatus.PROCESSING]),
                    Resume.updated_at < cutoff,
                )
            )
            .tuples()
            .all()
        )

        requeued = 0
        for resume_id, data_gone in stuck:
            if data_gone:
                resume = session.get(Resume, resume_id)
                if resume is not None:
                    resume.status = ParseStatus.FAILED
                    resume.error_message = (
                        "Processing was interrupted and the file is no longer available. "
                        "Please upload it again."
                    )
                continue
            # Enqueue after the loop's session commits? No — the message may only race the
            # commit in the *upload* path. Here the row is already committed and old; sending
            # first is harmless because the worker (this same process) handles messages
            # sequentially after the sweep finishes.
            parse_resume.delay(str(resume_id))
            requeued += 1

    if stuck:
        logger.warning(
            "requeue_stuck_resumes: %d stuck, %d re-enqueued, %d failed (file gone)",
            len(stuck),
            requeued,
            len(stuck) - requeued,
        )
    return requeued
