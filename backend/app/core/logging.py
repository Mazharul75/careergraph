"""Structured logging configuration.

**Structured logging** means each log line is a set of key-value pairs rather than a prose
sentence. ``logger.info("request completed", status_code=200, duration_ms=12.3)`` renders in
production as one JSON object — so a log platform can *query* it ("all requests over 500 ms
yesterday") instead of regex-matching prose. Think of the difference between a spreadsheet
and a diary: both record the same events, but only one can be filtered and aggregated.

**structlog** is the library that does this. It sits in front of Python's stdlib ``logging``
rather than replacing it, which matters here: uvicorn, celery, and sqlalchemy all log through
stdlib. The ``ProcessorFormatter`` bridge below routes *their* records through the same
renderer, so the whole process emits one consistent format — JSON in production, colored
human-readable lines in development.

Called once at process start: from ``create_app()`` for the API, from Celery's
``setup_logging`` signal for the worker.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(*, log_level: str, environment: str) -> None:
    """Set up structlog and route stdlib logging through it.

    JSON when the output is for machines (staging/production, where Render captures stdout
    and a log platform consumes it), pretty console lines when it is for humans.
    """
    # Processors that run for every event, wherever it came from. Order matters: each one
    # transforms the event dict and passes it on — a pipeline, exactly like middleware.
    shared_processors: list[structlog.typing.Processor] = [
        # Pulls in whatever the request middleware bound (request_id, method, path), which
        # is how one request's every log line carries the same correlation id.
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    renderer: structlog.typing.Processor
    if environment in ("staging", "production"):
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    # The bridge: stdlib LogRecords (uvicorn, celery, sqlalchemy, and our own modules that
    # use logging.getLogger) get run through the same processors and renderer as structlog's
    # native events. Without this, production logs would be a mix of JSON and prose — the
    # worst of both.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Replace, don't append: configure_logging may run more than once in tests, and
    # accumulating handlers double-prints every line.
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.StackInfoRenderer(),
            # Hands the event to the stdlib handler above instead of printing directly, so
            # native structlog events and foreign records leave through one pipe.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
