"""Refresh tokens: one row per issued token, grouped into sessions by `session_id`."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Every token issued since one Google login shares this id: rotation keeps
    # it, and reuse of an old token revokes the whole session through it
    session_id: Mapped[uuid.UUID] = mapped_column(index=True)
    # SHA-256 of the token; the token itself is never stored
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Sliding expiry: REFRESH_TOKEN_DAYS after issue, never after session_expires_at
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Absolute end of the session: SESSION_MAX_DAYS after the Google login
    session_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Set when the token is rotated or the session is logged out or revoked
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
