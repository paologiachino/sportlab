"""What the API returns about a user."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import UserRole, UserStatus


class UserOut(BaseModel):
    """The signed-in user, as returned by GET /api/auth/me.

    Only the fields listed here leave the server: internal columns added to the
    users table later never reach the API by accident.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str | None
    status: UserStatus
    role: UserRole


class UserAdminOut(UserOut):
    """A user as administrators see it in the user list."""

    created_at: datetime
    last_login_at: datetime | None
    approved_at: datetime | None
    approved_by: uuid.UUID | None


class RoleChange(BaseModel):
    """Body of POST /api/admin/users/{user_id}/role."""

    role: UserRole
