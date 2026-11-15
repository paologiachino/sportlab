"""Sessions: the chain of refresh tokens started by one Google login.

- start_session: after a login, issues the first refresh token of a new session.
- rotate: exchanges a refresh token for a new one (the old one is revoked).
  Presenting an already revoked token means it was copied: the whole session is
  revoked, so neither the thief nor the owner can go on with it.
- end_session: logout, revokes every token of the session.

Every function commits its own changes, so a revocation is saved even when the
call then fails with an error. `now` can be passed to test expiry deterministically.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import hash_refresh_token, new_refresh_token
from app.models import RefreshToken


class InvalidRefreshTokenError(Exception):
    """Unknown, expired or revoked refresh token: the person must sign in again."""


class RefreshTokenReuseError(InvalidRefreshTokenError):
    """A revoked token was presented again: the session has been revoked."""


@dataclass(frozen=True)
class SessionLifetimes:
    refresh: timedelta  # sliding: REFRESH_TOKEN_DAYS
    session: timedelta  # absolute: SESSION_MAX_DAYS


@dataclass(frozen=True)
class IssuedToken:
    user_id: uuid.UUID
    session_id: uuid.UUID
    token: str  # the plain token, for the cookie; never stored
    expires_at: datetime


def _issue(
    db: Session,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    session_expires_at: datetime,
    lifetimes: SessionLifetimes,
    now: datetime,
) -> IssuedToken:
    token = new_refresh_token()
    # Sliding expiry, but never beyond the end of the session
    expires_at = min(now + lifetimes.refresh, session_expires_at)
    db.add(
        RefreshToken(
            user_id=user_id,
            session_id=session_id,
            token_hash=hash_refresh_token(token),
            expires_at=expires_at,
            session_expires_at=session_expires_at,
        )
    )
    return IssuedToken(user_id, session_id, token, expires_at)


def start_session(
    db: Session, user_id: uuid.UUID, lifetimes: SessionLifetimes, now: datetime | None = None
) -> IssuedToken:
    now = now or datetime.now(UTC)
    issued = _issue(db, user_id, uuid.uuid4(), now + lifetimes.session, lifetimes, now)
    db.commit()
    return issued


def _revoke_session(db: Session, session_id: uuid.UUID, now: datetime) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.session_id == session_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def rotate(
    db: Session, token: str, lifetimes: SessionLifetimes, now: datetime | None = None
) -> IssuedToken:
    """A new refresh token in place of `token`, in the same session."""
    now = now or datetime.now(UTC)
    # FOR UPDATE: two requests rotating the same token are handled one at a
    # time, so only the first succeeds and the second is seen as a reuse
    current = db.scalars(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(token))
        .with_for_update()
    ).one_or_none()

    if current is None:
        db.rollback()
        raise InvalidRefreshTokenError("unknown token")

    if current.revoked_at is not None:
        _revoke_session(db, current.session_id, now)
        db.commit()
        raise RefreshTokenReuseError("revoked token presented again")

    if current.expires_at <= now or current.session_expires_at <= now:
        db.rollback()
        raise InvalidRefreshTokenError("expired token")

    current.revoked_at = now
    issued = _issue(
        db, current.user_id, current.session_id, current.session_expires_at, lifetimes, now
    )
    db.commit()
    return issued


def end_session(db: Session, token: str, now: datetime | None = None) -> None:
    """Logout: revoke the session of `token`. Unknown tokens are ignored."""
    now = now or datetime.now(UTC)
    session_id = db.scalar(
        select(RefreshToken.session_id).where(RefreshToken.token_hash == hash_refresh_token(token))
    )
    if session_id is not None:
        _revoke_session(db, session_id, now)
    db.commit()


def end_all_sessions(db: Session, user_id: uuid.UUID, now: datetime | None = None) -> None:
    """Revoke every session of a user (for example when an admin disables them)."""
    now = now or datetime.now(UTC)
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.commit()
