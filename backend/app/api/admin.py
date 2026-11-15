"""User administration, for active administrators only.

- GET  /api/admin/users?status=pending   list users, optionally by status
- POST /api/admin/users/{user_id}/approve  pending or disabled -> active
- POST /api/admin/users/{user_id}/disable  -> disabled, sessions revoked
- POST /api/admin/users/{user_id}/role     {"role": "admin" | "user"}

404 for an unknown user; 409 when the action does not fit the user's state,
including removing the last active administrator.
"""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import AdminUser
from app.db.session import get_db
from app.models import User, UserStatus
from app.schemas.user import RoleChange, UserAdminOut
from app.services import admin as service

router = APIRouter(prefix="/admin/users", tags=["admin"])

DbDep = Annotated[Session, Depends(get_db)]


def _run(action: Callable[[], User]) -> UserAdminOut:
    """Run a service action and map its errors to HTTP answers."""
    try:
        return UserAdminOut.model_validate(action())
    except service.UserNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found") from None
    except service.AdminActionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None


@router.get("")
def list_users(
    admin: AdminUser,
    db: DbDep,
    # ?status=pending in the URL; another name in the code, so it does not hide
    # FastAPI's `status` module used for the HTTP codes
    status_filter: Annotated[UserStatus | None, Query(alias="status")] = None,
) -> list[UserAdminOut]:
    return [UserAdminOut.model_validate(user) for user in service.list_users(db, status_filter)]


@router.post("/{user_id}/approve")
def approve(user_id: uuid.UUID, admin: AdminUser, db: DbDep) -> UserAdminOut:
    return _run(lambda: service.approve(db, admin, user_id))


@router.post("/{user_id}/disable")
def disable(user_id: uuid.UUID, admin: AdminUser, db: DbDep) -> UserAdminOut:
    return _run(lambda: service.disable(db, admin, user_id))


@router.post("/{user_id}/role")
def set_role(user_id: uuid.UUID, body: RoleChange, admin: AdminUser, db: DbDep) -> UserAdminOut:
    return _run(lambda: service.set_role(db, admin, user_id, body.role))
