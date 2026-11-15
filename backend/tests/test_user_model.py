"""The users table, as created by the migrations, enforces its rules.

All accounts are synthetic: generated `sub` values and example.com addresses.
"""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User, UserRole, UserStatus


def new_user(**fields: object) -> User:
    """A synthetic user; any field can be overridden."""
    sub = uuid.uuid4().hex
    values: dict[str, object] = {"google_sub": sub, "email": f"user-{sub[:8]}@example.com"}
    values.update(fields)
    return User(**values)


@pytest.fixture
def session(migrated_database: Engine) -> Iterator[Session]:
    with Session(migrated_database) as session:
        yield session


def test_new_user_defaults(session: Session) -> None:
    user = new_user()
    session.add(user)
    session.commit()

    assert isinstance(user.id, uuid.UUID)
    assert user.status == UserStatus.PENDING
    assert user.role == UserRole.USER
    assert user.created_at is not None
    assert user.approved_at is None
    assert user.approved_by is None


def test_google_sub_is_unique(session: Session) -> None:
    session.add(new_user(google_sub="synthetic-sub-1"))
    session.commit()

    session.add(new_user(google_sub="synthetic-sub-1"))
    with pytest.raises(IntegrityError, match="uq_users_google_sub"):
        session.commit()


def test_same_email_on_two_google_accounts_is_allowed(session: Session) -> None:
    """The email is not the identity: a Google account can change address."""
    session.add_all([new_user(email="shared@example.com"), new_user(email="shared@example.com")])
    session.commit()

    assert len(session.scalars(select(User).where(User.email == "shared@example.com")).all()) == 2


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("status", "approved", "ck_users_status"),
        ("role", "superuser", "ck_users_role"),
        ("email", "Mixed.Case@example.com", "ck_users_email_lowercase"),
    ],
)
def test_check_constraints(session: Session, field: str, value: str, constraint: str) -> None:
    session.add(new_user(**{field: value}))
    with pytest.raises(IntegrityError, match=constraint):
        session.commit()


def test_every_status_and_role_is_accepted(session: Session) -> None:
    session.add_all(
        [new_user(status=status, role=role) for status in UserStatus for role in UserRole]
    )
    session.commit()


def test_approver_deletion_keeps_the_approved_user(session: Session) -> None:
    admin = new_user(role=UserRole.ADMIN, status=UserStatus.ACTIVE)
    session.add(admin)
    session.flush()
    approved = new_user(status=UserStatus.ACTIVE, approved_by=admin.id)
    session.add(approved)
    session.commit()

    session.execute(text("DELETE FROM users WHERE id = :id"), {"id": admin.id})
    session.commit()
    session.refresh(approved)

    assert approved.approved_by is None
    assert approved.status == UserStatus.ACTIVE
