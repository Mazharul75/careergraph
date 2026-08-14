"""Health and readiness probes.

These live at the root, not under ``/api/v1``. Platform health checks are infrastructure
concerns and must not move when the API is versioned.

**Liveness vs readiness** — these answer different questions and a platform reacts to them
differently:

* ``/health`` (liveness): is the process alive? It touches nothing external. If this fails the
  process is wedged and should be *restarted*.
* ``/health/ready`` (readiness): can the process serve traffic right now? It checks
  dependencies. If this fails the instance should be *taken out of the load balancer* but not
  killed — the database may simply be failing over, and restarting the API would not help.

Conflating the two produces a restart loop during any brief database outage: the app is
perfectly healthy, gets marked unhealthy, gets killed, and the outage becomes worse.

**Not every dependency is critical.** Postgres down means nothing can be served, so readiness
fails. Redis down means the *queue* is dead — uploads are accepted and never processed — while
every read still works perfectly. Failing readiness for that would take a mostly-working
service out of rotation; reporting it as degraded surfaces the problem without making it worse.

That distinction is not hypothetical: a deployment missing ``REDIS_URL`` boots cleanly, serves
reads, retries Redis in the background, and would report ``ready`` under a Postgres-only probe
while every resume silently stayed in ``pending``.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import get_settings
from app.schemas.health import DependencyStatus, HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])

_VERSION = "0.1.0"

# How long a dependency check may take before it is treated as down. A probe that hangs is
# worse than one that fails: the platform waits, then kills a process that was merely slow.
_PROBE_TIMEOUT_SECONDS = 3.0


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        service=settings.project_name,
        version=_VERSION,
        environment=settings.environment,
    )


async def _check_postgres(session: DbSession) -> DependencyStatus:
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
            await session.execute(text("SELECT 1"))
        return DependencyStatus(name="postgres", healthy=True, critical=True)
    except Exception as exc:  # a probe must report any failure, not a chosen subset
        # The exception type is reported, never the message: connection errors routinely
        # contain the host, port, and username, and this endpoint is unauthenticated.
        return DependencyStatus(
            name="postgres", healthy=False, critical=True, detail=type(exc).__name__
        )


async def _check_redis() -> DependencyStatus:
    """Ping the broker.

    Imported inside the function so the API process does not pay for a redis client at import
    time, and so a missing dependency degrades this one probe rather than failing startup.
    """
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(get_settings().broker_url)
        try:
            async with asyncio.timeout(_PROBE_TIMEOUT_SECONDS):
                await client.ping()
            return DependencyStatus(name="redis", healthy=True, critical=False)
        finally:
            await client.aclose()
    except Exception as exc:
        return DependencyStatus(
            name="redis", healthy=False, critical=False, detail=type(exc).__name__
        )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"description": "A critical dependency is unavailable"}},
)
async def readiness(session: DbSession, response: Response) -> ReadinessResponse:
    # Checked concurrently: two sequential probes with a 3s timeout each could take 6s, and a
    # platform health check that slow gets treated as a failure.
    postgres, redis = await asyncio.gather(_check_postgres(session), _check_redis())
    dependencies = [postgres, redis]

    critical_failure = any(dep.critical and not dep.healthy for dep in dependencies)
    degraded = any(not dep.healthy for dep in dependencies)

    if critical_failure:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="unavailable" if critical_failure else "degraded" if degraded else "ready",
        dependencies=dependencies,
    )
