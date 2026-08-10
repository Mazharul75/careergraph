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
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import get_settings
from app.schemas.health import DependencyStatus, HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])

_VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        service=settings.project_name,
        version=_VERSION,
        environment=settings.environment,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"description": "One or more dependencies are unavailable"}},
)
async def readiness(session: DbSession, response: Response) -> ReadinessResponse:
    dependencies: list[DependencyStatus] = []

    try:
        await session.execute(text("SELECT 1"))
        dependencies.append(DependencyStatus(name="postgres", healthy=True))
    except Exception as exc:  # a probe must report any failure, not a chosen subset
        # The exception type is reported, never the message: connection errors routinely
        # contain the host, port, and username, and this endpoint is unauthenticated.
        dependencies.append(
            DependencyStatus(name="postgres", healthy=False, detail=type(exc).__name__)
        )

    all_healthy = all(dep.healthy for dep in dependencies)
    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if all_healthy else "degraded",
        dependencies=dependencies,
    )
