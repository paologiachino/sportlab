"""User administration: approve, disable, promote and demote.

The last active administrator can be neither disabled nor demoted. Two admins
demoting each other at the same moment must not leave the site with none, so
every action first locks the rows of all active administrators (always in the
same order, by id, so two actions cannot deadlock), then the target user. A
concurrent action waits for the lock and then sees the up-to-date count.

Every function commits its own changes; the caller passes the acting admin.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserRole, UserStatus
from app.services.sessions import revoke_all_sessions

logger = logging.getLogger(__name__)


class UserNotFoundError(Exception):
    pass


class AdminActionError(Exception):
    """The action is not possible in the user's current state (HTTP 409)."""


class LastAdminError(AdminActionError):
    """The action would leave no active administrator."""


def _lock_active_admins(db: Session) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(User.id)
            .where(User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE)
            .order_by(User.id)
            .with_for_update()
        )
    )


def _lock_target(db: Session, user_id: uuid.UUID) -> User:
    user = db.scalars(select(User).where(User.id == user_id).with_for_update()).one_or_none()
    if user is None:
        db.rollback()
        raise UserNotFoundError(str(user_id))
    return user


def _refuse(db: Session, error: AdminActionError) -> AdminActionError:
    db.rollback()  # release the locks
    return error


def _guard_last_admin(db: Session, target: User, active_admins: list[uuid.UUID]) -> None:
    if target.id in active_admins and len(active_admins) == 1:
        raise _refuse(db, LastAdminError("the last active administrator cannot be removed"))


def list_users(db: Session, status: UserStatus | None = None) -> list[User]:
    query = select(User).order_by(User.created_at, User.id)
    if status is not None:
        query = query.where(User.status == status)
    return list(db.scalars(query))


def approve(db: Session, actor: User, user_id: uuid.UUID, now: datetime | None = None) -> User:
    """Pending or disabled -> active; records who approved and when."""
    now = now or datetime.now(UTC)
    _lock_active_admins(db)
    user = _lock_target(db, user_id)
    if user.status == UserStatus.ACTIVE:
        raise _refuse(db, AdminActionError("the user is already active"))
    user.status = UserStatus.ACTIVE
    user.approved_at = now
    user.approved_by = actor.id
    db.commit()
    logger.info("User %s approved by %s", user.id, actor.id)
    return user


def disable(db: Session, actor: User, user_id: uuid.UUID, now: datetime | None = None) -> User:
    """Pending or active -> disabled, and every session of the user is revoked."""
    now = now or datetime.now(UTC)
    active_admins = _lock_active_admins(db)
    user = _lock_target(db, user_id)
    if user.status == UserStatus.DISABLED:
        raise _refuse(db, AdminActionError("the user is already disabled"))
    _guard_last_admin(db, user, active_admins)
    user.status = UserStatus.DISABLED
    # Same transaction: disabled and signed out together, or neither
    revoke_all_sessions(db, user.id, now)
    db.commit()
    logger.info("User %s disabled by %s", user.id, actor.id)
    return user


def set_role(db: Session, actor: User, user_id: uuid.UUID, role: UserRole) -> User:
    """Promote to admin (active users only) or demote to user (not the last admin)."""
    active_admins = _lock_active_admins(db)
    user = _lock_target(db, user_id)
    if user.role == role:
        raise _refuse(db, AdminActionError(f"the user is already {role}"))
    if role == UserRole.ADMIN and user.status != UserStatus.ACTIVE:
        raise _refuse(db, AdminActionError("only active users can become administrators"))
    if role == UserRole.USER:
        _guard_last_admin(db, user, active_admins)
    user.role = role
    db.commit()
    logger.info("User %s set to %s by %s", user.id, role, actor.id)
    return user
