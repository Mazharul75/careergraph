"""The concrete task dispatcher.

Satisfies ``TaskDispatcher`` from ``app/repositories/protocols.py``. Keeping the Celery import
behind this thin adapter is what lets ``ResumeService`` be unit-tested with a recorder object
and no broker running.
"""

from __future__ import annotations

import uuid

from app.workers.tasks import parse_resume


class CeleryTaskDispatcher:
    def enqueue_resume_parse(self, resume_id: uuid.UUID) -> None:
        # `.delay()` publishes to Redis and returns immediately — it does not wait for a worker
        # to pick the message up, or even to exist.
        parse_resume.delay(str(resume_id))
