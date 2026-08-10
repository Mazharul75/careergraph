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
    detail: str | None = Field(default=None, examples=[None])


class ReadinessResponse(BaseModel):
    """Readiness: is this process able to *serve traffic*, dependencies included?"""

    status: Literal["ready", "degraded"]
    dependencies: list[DependencyStatus]
