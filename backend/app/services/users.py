"""Users after a Google sign-in: create them, or refresh what Google says about them."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User, UserRole, UserStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GoogleIdentity:
    """The verified claims of a Google ID token that sportlab uses."""

    sub: str
    email: str
    display_name: str | None


def _find(db: Session, sub: str) -> User | None:
    return db.scalars(select(User).where(User.google_sub == sub)).one_or_none()


def sign_in(
    db: Session, identity: GoogleIdentity, admin_email: str | None, now: datetime | None = None
) -> User:
    """The user for a verified Google identity, created on the first sign-in.

    A new account is pending, unless its email is ADMIN_EMAIL: then it is an
    active administrator. This happens only at creation, so an administrator
    demoted by another one does not become admin again by signing in.
    """
    now = now or datetime.now(UTC)
    email = identity.email.strip().lower()

    user = _find(db, identity.sub)
    if user is None:
        is_admin = admin_email is not None and email == admin_email
        user = User(
            google_sub=identity.sub,
            email=email,
            display_name=identity.display_name,
            status=UserStatus.ACTIVE if is_admin else UserStatus.PENDING,
            role=UserRole.ADMIN if is_admin else UserRole.USER,
            last_login_at=now,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # The same account signing in twice at the same moment: the other
            # request created it first, so use that row
            db.rollback()
            user = _find(db, identity.sub)
            if user is None:
                raise
        else:
            # The user id only: no email or name in the logs
            logger.info("New user %s (%s, %s)", user.id, user.status, user.role)
            return user

    # Existing account: status and role are never changed by a sign-in
    user.email = email
    user.display_name = identity.display_name
    user.last_login_at = now
    db.commit()
    return user
