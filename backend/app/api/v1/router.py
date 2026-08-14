"""Aggregate router for API v1.

Feature routers are registered here and this single router is mounted in ``main.py``. That
keeps the application factory from growing an import per endpoint group, and makes the full
v1 surface visible in one file.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, jobs, matches, paths, resumes, skills

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(resumes.router, prefix="/resumes", tags=["resumes"])
api_router.include_router(skills.router, prefix="/skills", tags=["skills"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
# Mounted under /jobs too: a match is a property of a job, not its own resource.
api_router.include_router(matches.router, prefix="/jobs", tags=["matches"])
# Declares its own full paths, since it spans both /jobs and /skills.
api_router.include_router(paths.router)
