"""Celery application.

**Why a task queue at all?** Parsing a PDF takes seconds. A request that does it inline holds a
worker process the entire time, so a handful of simultaneous uploads stall every other request
on the server. The queue turns "do this now, while the user waits" into "write down that this
needs doing, and answer immediately" — like a restaurant order ticket: the waiter does not stand
at the pass while your food cooks.

The API writes a message to Redis and returns `202 Accepted`. A separate worker process picks it
up whenever it can. Neither has to be running for the other to work: if the worker is down,
messages queue up and drain when it returns.
"""

from __future__ import annotations

from typing import Any

from celery import Celery
from celery.signals import setup_logging

from app.core.config import get_settings
from app.core.logging import configure_logging

_settings = get_settings()

celery_app = Celery(
    "careergraph",
    broker=_settings.broker_url,
    # `include` is how the worker discovers task functions. Without it, the worker starts
    # cleanly, receives the message, and rejects it as unregistered — a confusing failure,
    # because nothing looks broken until you read the worker log.
    include=["app.workers.tasks", "app.workers.maintenance"],
)


@setup_logging.connect
def _configure_worker_logging(**_kwargs: Any) -> None:
    """Give the worker the same structured logging as the API.

    Connecting *any* receiver to this signal also stops Celery from hijacking the root
    logger with its own format — which it does by default, and which would silently undo
    the JSON configuration in production.
    """
    configure_logging(log_level=_settings.log_level, environment=_settings.environment)


celery_app.conf.update(
    # --- Serialization -----------------------------------------------------------------
    # JSON only. Celery's original default was pickle, which executes arbitrary code on
    # deserialization — anyone able to write to the broker gets remote code execution.
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # --- Results ------------------------------------------------------------------------
    # No result backend. Parse status lives in the `resumes` table, because it is something
    # the user asks about through the API — not an implementation detail of the queue. Storing
    # it twice would let the two disagree, and Celery results expire while a resume does not.
    task_ignore_result=True,
    # --- Delivery guarantees ------------------------------------------------------------
    # Acknowledge a message only after the task finishes, not when it is received. If the
    # worker is killed mid-parse — which free hosting does routinely — the message returns to
    # the queue instead of vanishing. The price is that a task may run twice, which is why
    # every task is written to be idempotent.
    task_acks_late=True,
    # Fetch one message at a time. The default prefetches several per worker, which with
    # acks_late means a crash re-runs everything held in that buffer. At our volume, batching
    # buys nothing and costs redundant work.
    worker_prefetch_multiplier=1,
    # --- Timeouts -------------------------------------------------------------------------
    # soft raises inside the task so it can record a failure; hard kills the process. Without
    # a limit, one malformed PDF that sends a parser into a loop occupies the only worker
    # forever, and every later upload silently stops being processed.
    task_soft_time_limit=120,
    task_time_limit=180,
    # --- Worker lifecycle -----------------------------------------------------------------
    worker_max_tasks_per_child=_settings.celery_max_tasks_per_child,
    worker_concurrency=_settings.celery_concurrency,
    # --- Broker connection ------------------------------------------------------------------
    # The worker and Redis start at the same moment in Docker and on Render, so the first
    # connection attempt often loses the race. Retrying on startup avoids a crash loop.
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        # Redis has no native acknowledgement, so Celery emulates `task_acks_late` with a
        # timer: a delivered-but-unacknowledged message is handed to another worker only
        # after this many seconds. The default is **one hour**, which means a worker killed
        # mid-task leaves its job invisible for an hour — long enough to look like a
        # permanent hang rather than a retry.
        #
        # Ten minutes instead. The floor is the hard time limit (180 s): set this below the
        # longest a task may legitimately run and a still-running task gets handed to a
        # second worker and executed twice.
        "visibility_timeout": 600,
    },
    timezone="UTC",
    enable_utc=True,
    # --- Periodic maintenance (celery beat, embedded via the worker's -B flag) -----------
    beat_schedule={
        # Daily is plenty: the table grows by one row per login, and the sweep is a single
        # indexed DELETE.
        "purge-expired-refresh-tokens": {
            "task": "maintenance.purge_expired_refresh_tokens",
            "schedule": 24 * 60 * 60.0,
        },
        # Every 10 minutes, against a 15-minute stuck threshold: a lost resume is repaired
        # within ~25 minutes worst case, while a healthy queue makes this a no-op SELECT.
        "requeue-stuck-resumes": {
            "task": "maintenance.requeue_stuck_resumes",
            "schedule": 10 * 60.0,
        },
    },
    # Beat persists its "last run" bookkeeping to a small file. The container filesystem is
    # read-only-ish for the app user at /app, and the file is disposable state — /tmp is
    # exactly right. Losing it on restart merely re-baselines the schedule.
    beat_schedule_filename="/tmp/celerybeat-schedule",  # noqa: S108
)
