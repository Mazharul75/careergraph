"""Celery task definitions.

Tasks are thin. They own transaction boundaries and failure handling; the actual work lives in
``app/services/extraction.py`` as pure functions, so the interesting logic is unit-testable
without Celery, Redis, or a database.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from app.db.sync_session import worker_session
from app.models.job import Job
from app.models.resume import ParseStatus, Resume
from app.models.skill import Skill
from app.models.user_skill import SkillSource, SkillStatus, UserSkill
from app.repositories.skill import to_vocabulary
from app.services.embedding import embed_text
from app.services.extraction import ExtractionError, extract_text
from app.services.skill_matching import SkillMatcher
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Truncated to fit the column, and because a user-facing message should be short.
_MAX_ERROR_LENGTH = 500


def _fail(resume: Resume, message: str) -> None:
    resume.status = ParseStatus.FAILED
    resume.error_message = message[:_MAX_ERROR_LENGTH]
    # Drop the bytes even on failure. Retrying would fail identically — the file is malformed,
    # not unlucky — so holding a megabyte of unusable PDF forever serves nobody.
    resume.file_data = None


@celery_app.task(name="resumes.parse", bind=True, max_retries=2, default_retry_delay=30)
def parse_resume(self: Any, resume_id: str) -> str:
    """Extract text from an uploaded resume.

    **Idempotent by construction.** ``task_acks_late`` means a worker that dies mid-parse gets
    the message redelivered, so this may run more than once for the same resume. Both guards
    below make a repeat run harmless:

    * already ``complete`` → return immediately, do no work
    * ``file_data`` already cleared → nothing to parse, so do not overwrite a good result

    Returns a short status string purely for the worker log; nothing consumes it, because
    ``task_ignore_result`` is on and the real status lives in the database.
    """
    resume_uuid = uuid.UUID(resume_id)

    with worker_session() as session:
        resume = session.get(Resume, resume_uuid)

        if resume is None:
            # The user deleted it between enqueue and execution. Not an error worth retrying.
            logger.warning("parse_resume: resume %s no longer exists", resume_id)
            return "missing"

        if resume.status is ParseStatus.COMPLETE:
            logger.info("parse_resume: resume %s already complete, skipping", resume_id)
            return "already-complete"

        if resume.file_data is None:
            _fail(resume, "The uploaded file is no longer available for parsing.")
            return "no-data"

        resume.status = ParseStatus.PROCESSING
        # Commit the status change on its own so a client polling right now sees `processing`
        # rather than sitting on `pending` for the whole parse.
        session.commit()

        data = resume.file_data

        try:
            _kind, text = extract_text(data)

        except ExtractionError as exc:
            # A bad document, not a broken system. Retrying cannot help, so fail terminally
            # with the user-safe message the extractor produced.
            logger.info("parse_resume: resume %s unparseable: %s", resume_id, exc)
            _fail(resume, str(exc))
            return "failed"

        except SoftTimeLimitExceeded:
            logger.error("parse_resume: resume %s exceeded the time limit", resume_id)
            _fail(resume, "Parsing took too long. The document may be unusually large.")
            return "timeout"

        except Exception as exc:
            # Something unexpected — a library bug, a transient database blip. This one *is*
            # worth retrying, because a later attempt might succeed.
            logger.exception("parse_resume: unexpected failure for resume %s", resume_id)
            try:
                raise self.retry(exc=exc) from exc
            except self.MaxRetriesExceededError:
                _fail(resume, "Parsing failed unexpectedly. Please try uploading again.")
                return "failed"

        # Skills are extracted in the same transaction as the text. If this were a second
        # queued task, a resume could sit in `complete` with an empty profile whenever the
        # follow-up failed — a state the UI would have no way to explain.
        try:
            skill_count = _extract_skills(session, resume.user_id, text)
        except Exception:
            # Text extraction succeeded and is worth keeping. A failure here degrades the
            # result rather than destroying it, so it is logged and the parse still completes;
            # re-uploading re-runs extraction.
            logger.exception("parse_resume: skill extraction failed for resume %s", resume_id)
            skill_count = 0

        # Embedding is the expensive step (~200 MB of model, see ADR-0009) and it is best
        # effort: a resume with text and skills but no vector still scores, just on skills
        # alone. Failing the whole parse because the model could not load would throw away
        # work that already succeeded.
        try:
            resume.embedding = embed_text(text)
        except Exception:
            logger.exception("parse_resume: embedding failed for resume %s", resume_id)

        resume.extracted_text = text
        resume.status = ParseStatus.COMPLETE
        resume.error_message = None
        # The original bytes have served their purpose. Dropping them keeps the free-tier
        # database small and means a database compromise exposes far less than the resumes
        # themselves — we keep the text we need, not the document the user handed us.
        resume.file_data = None

        logger.info(
            "parse_resume: resume %s complete, %d characters, %d skills",
            resume_id,
            len(text),
            skill_count,
        )
        return "complete"


def _extract_skills(session: Session, user_id: uuid.UUID, text: str) -> int:
    """Match the vocabulary against the text and record the results.

    Synchronous, because this runs inside a Celery worker (ADR-0005). Uses the same models and
    the same matcher as the API — only the session type differs.
    """
    skills = session.execute(select(Skill).options(selectinload(Skill.aliases))).scalars().all()
    matcher = SkillMatcher.build(to_vocabulary(list(skills)))
    found = matcher.find(text)
    if not found:
        return 0

    # Skills the user has explicitly dismissed. Filtering them out here — rather than relying
    # on the upsert's WHERE clause alone — keeps rejected suggestions from reappearing at all.
    rejected = set(
        session.execute(
            select(UserSkill.skill_id).where(
                UserSkill.user_id == user_id, UserSkill.status == SkillStatus.REJECTED
            )
        ).scalars()
    )

    rows = [
        {
            "user_id": user_id,
            "skill_id": match.skill_id,
            "source": SkillSource.EXTRACTED,
            "status": SkillStatus.SUGGESTED,
            "occurrences": min(match.occurrences, 32767),
        }
        for match in found
        if match.skill_id not in rejected
    ]
    if not rows:
        return 0

    stmt = pg_insert(UserSkill).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[UserSkill.user_id, UserSkill.skill_id],
        set_={"occurrences": stmt.excluded.occurrences},
        # Re-uploading a resume must never silently undo a confirmation or a proficiency the
        # user set by hand, so only untouched suggestions are refreshed.
        where=UserSkill.status == SkillStatus.SUGGESTED,
    )
    session.execute(stmt)
    return len(rows)


@celery_app.task(name="jobs.embed", bind=True, max_retries=2, default_retry_delay=30)
def embed_job(self: Any, job_id: str) -> str:
    """Compute and store a job description's embedding.

    A separate task from job creation because creation is synchronous and fast (skill matching
    takes milliseconds) while embedding needs a 200 MB model. The job is fully usable for
    skill-based scoring the moment it is created; the semantic component appears when this
    finishes.

    Idempotent: recomputing an embedding for the same text yields the same vector.
    """
    job_uuid = uuid.UUID(job_id)

    with worker_session() as session:
        job = session.get(Job, job_uuid)
        if job is None:
            logger.warning("embed_job: job %s no longer exists", job_id)
            return "missing"

        try:
            # Title and description together, matching how skills are extracted, so the two
            # signals describe the same text rather than subtly different documents.
            job.embedding = embed_text(f"{job.title}\n{job.description}")
        except SoftTimeLimitExceeded:
            logger.error("embed_job: job %s exceeded the time limit", job_id)
            return "timeout"
        except Exception as exc:
            logger.exception("embed_job: failed for job %s", job_id)
            try:
                raise self.retry(exc=exc) from exc
            except self.MaxRetriesExceededError:
                return "failed"

        logger.info("embed_job: job %s embedded", job_id)
        return "complete"
