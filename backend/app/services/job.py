"""Job description logic.

Skill extraction runs **inline** here, unlike resume parsing which goes on the queue. That is a
deliberate distinction, not an inconsistency: matching a compiled vocabulary against a few
kilobytes of pasted text takes single-digit milliseconds, while parsing a PDF takes seconds.
The queue exists for work that is slow, not for work that is merely asynchronous-looking. Phase
2c adds embedding generation for jobs, which *is* slow — that will go on the queue, and the job
stays usable for skill matching in the meantime.
"""

from __future__ import annotations

import uuid

from app.models.job import Job
from app.models.user import User, UserRole
from app.repositories.protocols import (
    JobRepositoryProtocol,
    SkillRepositoryProtocol,
    TaskDispatcher,
    UnitOfWork,
)
from app.services.exceptions import (
    JobNotFoundError,
    NotYourJobError,
    RecruiterRoleRequiredError,
)
from app.services.skill_matching import SkillMatcher

# Occurrence count → importance. A skill named once is probably a "nice to have"; one named
# five times is the job. Crude and honest, and the thresholds are visible rather than buried in
# a model nobody can inspect.
_IMPORTANCE_BY_OCCURRENCES = ((5, 5), (3, 4), (2, 3), (1, 2))


def importance_for(occurrences: int) -> int:
    for threshold, importance in _IMPORTANCE_BY_OCCURRENCES:
        if occurrences >= threshold:
            return importance
    return 1


class JobService:
    def __init__(
        self,
        *,
        jobs: JobRepositoryProtocol,
        skills: SkillRepositoryProtocol,
        dispatcher: TaskDispatcher,
        uow: UnitOfWork,
    ) -> None:
        self._jobs = jobs
        self._skills = skills
        self._dispatcher = dispatcher
        self._uow = uow

    async def create(
        self,
        *,
        user: User,
        title: str,
        description: str,
        company: str | None = None,
        location: str | None = None,
        is_public: bool = False,
    ) -> Job:
        # Authorization lives here, not only on the route, because the rule is a business rule:
        # publishing a posting is a recruiter capability. A future Celery task or admin script
        # calling this service gets the same check for free.
        if is_public and user.role is not UserRole.RECRUITER:
            raise RecruiterRoleRequiredError

        job = Job(
            created_by=user.id,
            title=title.strip(),
            company=(company or None),
            location=(location or None),
            description=description.strip(),
            is_public=is_public,
        )
        self._jobs.add(job)
        await self._uow.flush()  # assign job.id before building the join rows

        await self._attach_skills(job)
        await self._uow.commit()

        # Embedding needs a 200 MB model, so it goes on the queue. The job is fully usable for
        # skill-based scoring immediately; the semantic component appears when the task lands.
        self._dispatcher.enqueue_job_embedding(job.id)
        return await self._reload(job.id)

    async def _attach_skills(self, job: Job) -> None:
        vocabulary = await self._skills.load_vocabulary()
        matcher = SkillMatcher.build(vocabulary)

        # Title and description together: a title like "Senior Kubernetes Engineer" often names
        # the single most important skill and may never repeat in the body.
        matches = matcher.find(f"{job.title}\n{job.description}")

        await self._jobs.replace_skills(
            job.id,
            [(match.skill_id, importance_for(match.occurrences)) for match in matches],
        )

    async def get(self, *, job_id: uuid.UUID, user: User) -> Job:
        job = await self._jobs.get_visible(job_id, user.id)
        if job is None:
            # Same error for "does not exist" and "private and not yours", so ids cannot be
            # enumerated.
            raise JobNotFoundError
        return job

    async def list_visible(self, *, user: User, limit: int = 50) -> list[Job]:
        """The user's own jobs plus every public posting."""
        return await self._jobs.list_visible(user.id, limit=limit)

    async def update(
        self,
        *,
        job_id: uuid.UUID,
        user: User,
        title: str | None = None,
        description: str | None = None,
        company: str | None = None,
        location: str | None = None,
    ) -> Job:
        job = await self._jobs.get_owned(job_id, user.id)
        if job is None:
            raise NotYourJobError

        if title is not None:
            job.title = title.strip()
        if company is not None:
            job.company = company or None
        if location is not None:
            job.location = location or None

        if description is not None:
            job.description = description.strip()
            # Re-extract: the skills are derived from the text, so stale skills after an edit
            # would silently misreport what the job requires.
            await self._attach_skills(job)
            reembed = True
        else:
            reembed = False

        await self._uow.commit()
        if reembed:
            # The text changed, so the stored vector describes something that no longer exists.
            self._dispatcher.enqueue_job_embedding(job.id)
        return await self._reload(job.id)

    async def _reload(self, job_id: uuid.UUID) -> Job:
        job = await self._jobs.reload(job_id)
        if job is None:  # pragma: no cover - only if the row vanished mid-request
            raise JobNotFoundError
        return job

    async def delete(self, *, job_id: uuid.UUID, user: User) -> None:
        job = await self._jobs.get_owned(job_id, user.id)
        if job is None:
            raise NotYourJobError
        await self._jobs.delete(job)
        await self._uow.commit()
