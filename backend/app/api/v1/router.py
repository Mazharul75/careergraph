"""Aggregate router for API v1.

Feature routers are registered here and this single router is mounted in ``main.py``. That
keeps the application factory from growing an import per endpoint group, and makes the full
v1 surface visible in one file.
"""

from __future__ import annotations

from fastapi import APIRouter

api_router = APIRouter()

# Registered from Phase 1b onward:
#   api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
#   api_router.include_router(resumes.router, prefix="/resumes", tags=["resumes"])
