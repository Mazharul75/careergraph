"""Operator contracts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.user import UserRole


class SystemStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_users: int
    job_seekers: int
    recruiters: int
    admins: int
    inactive_users: int
    total_jobs: int
    public_jobs: int
    total_resumes: int
    resumes_pending: int
    resumes_failed: int
    active_goals: int
    achieved_goals: int


class AdminUserResponse(BaseModel):
    """A user as an operator sees them.

    No ``password_hash`` field exists here, and that is not an oversight — a response model
    can only serialise what it declares, so the hash cannot leak through this endpoint even
    if someone later passes a full ORM ``User`` into it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool
    email_verified: bool
    has_password: bool
    created_at: datetime
    skill_count: int = 0
    resume_count: int = 0


class SetActiveRequest(BaseModel):
    is_active: bool


class SetRoleRequest(BaseModel):
    role: UserRole
