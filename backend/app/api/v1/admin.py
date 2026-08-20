"""Operator routes.

Every route here is gated by ``require_role(UserRole.ADMIN)`` declared at the *router* level
rather than per-endpoint. Declaring it once is what makes it impossible to add a new admin
route that forgets the guard — the most likely way this surface would ever spring a leak.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import AdminServiceDep, CurrentUser, require_role
from app.models.user import UserRole
from app.schemas.admin import (
    AdminUserResponse,
    SetActiveRequest,
    SetRoleRequest,
    SystemStatsResponse,
)

router = APIRouter(dependencies=[Depends(require_role(UserRole.ADMIN))])


@router.get("/stats", response_model=SystemStatsResponse, summary="Fleet-wide counts")
async def get_stats(admin: AdminServiceDep) -> SystemStatsResponse:
    return SystemStatsResponse.model_validate(await admin.stats())


@router.get("/users", response_model=list[AdminUserResponse], summary="All accounts")
async def list_users(
    admin: AdminServiceDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[AdminUserResponse]:
    rows = await admin.list_users(limit=limit, offset=offset)
    return [AdminUserResponse.model_validate(row) for row in rows]


@router.patch(
    "/users/{user_id}/active",
    response_model=AdminUserResponse,
    summary="Suspend or restore an account",
    responses={
        404: {"description": "No such user"},
        409: {"description": "You cannot suspend your own account"},
    },
)
async def set_active(
    user_id: uuid.UUID,
    payload: SetActiveRequest,
    current_user: CurrentUser,
    admin: AdminServiceDep,
) -> AdminUserResponse:
    """Takes effect immediately, including for already-issued tokens.

    ``get_current_user`` re-reads ``is_active`` from the database on every request, so a
    suspended user's unexpired JWT stops working on their next call rather than whenever it
    happens to expire.
    """
    user = await admin.set_active(actor=current_user, user_id=user_id, is_active=payload.is_active)
    return AdminUserResponse.model_validate(user)


@router.patch(
    "/users/{user_id}/role",
    response_model=AdminUserResponse,
    summary="Change a user's role",
    responses={
        404: {"description": "No such user"},
        409: {"description": "Refusing to remove the last admin"},
    },
)
async def set_role(
    user_id: uuid.UUID,
    payload: SetRoleRequest,
    current_user: CurrentUser,
    admin: AdminServiceDep,
) -> AdminUserResponse:
    user = await admin.set_role(actor=current_user, user_id=user_id, role=payload.role)
    return AdminUserResponse.model_validate(user)
