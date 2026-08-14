"""Health check response contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness: is this process running and able to answer HTTP?"""

    status: Literal["ok"] = "ok"
    service: str = Field(examples=["CareerGraph"])
    version: str = Field(examples=["0.1.0"])
    environment: str = Field(examples=["local"])


class DependencyStatus(BaseModel):
    name: str = Field(examples=["postgres"])
    healthy: bool
    critical: bool = Field(
        default=True,
        description=(
            "Whether the service can serve traffic without it. Postgres is critical — nothing "
            "works without it. Redis is not: reads still work, only background processing "
            "stops, so the service is degraded rather than unavailable."
        ),
    )
    detail: str | None = Field(
        default=None,
        description="Exception type on failure. Never a message — those leak hosts and users.",
        examples=[None],
    )


class ReadinessResponse(BaseModel):
    """Readiness: is this process able to *serve traffic*, dependencies included?

    Three states rather than two. `degraded` is the one that matters operationally: the API is
    answering correctly but something behind it is broken, which a boolean would either hide
    (by reporting ready) or over-report (by pulling a working instance out of rotation).
    """

    status: Literal["ready", "degraded", "unavailable"]
    dependencies: list[DependencyStatus]
