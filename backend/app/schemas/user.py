"""What the API returns about a user."""

import uuid

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
