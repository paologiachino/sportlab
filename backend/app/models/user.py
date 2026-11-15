"""Users: who can sign in, whether they are approved, and their role."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserStatus(StrEnum):
    PENDING = "pending"  # registered, waiting for an administrator
    ACTIVE = "active"  # approved
    DISABLED = "disabled"  # access removed by an administrator


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


def allowed_values(column: str, enum: type[StrEnum]) -> str:
    """SQL condition `column IN ('a', 'b')` built from a Python enum."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return f"{column} IN ({values})"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Text plus CHECK instead of a PostgreSQL ENUM: adding a value later is an
        # ordinary, reversible migration
        CheckConstraint(allowed_values("status", UserStatus), name="status"),
        CheckConstraint(allowed_values("role", UserRole), name="role"),
        # The application stores emails in lowercase; the database refuses others
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    # Google's stable account id (the "sub" claim): the identity, unlike the email
    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(200))

    status: Mapped[str] = mapped_column(String(16), server_default=UserStatus.PENDING.value)
    role: Mapped[str] = mapped_column(String(16), server_default=UserRole.USER.value)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Who approved the account; kept as NULL if that administrator is deleted
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
