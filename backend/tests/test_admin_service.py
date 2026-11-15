"""User administration rules, on a database built by the migrations."""

import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.models import RefreshToken, User, UserRole, UserStatus
from app.services import admin as service
from app.services.sessions import SessionLifetimes, start_session

NOW = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
LIFETIMES = SessionLifetimes(refresh=timedelta(days=30), session=timedelta(days=90))


@pytest.fixture
def db(migrated_database: Engine) -> Iterator[Session]:
    with Session(migrated_database) as session:
        yield session


def make_user(db: Session, status: str = UserStatus.ACTIVE, role: str = UserRole.USER) -> User:
    sub = uuid.uuid4().hex
    user = User(google_sub=sub, email=f"user-{sub[:8]}@example.com", status=status, role=role)
    db.add(user)
    db.commit()
    return user


def active_admin_count(db: Session) -> int:
    db.expire_all()
    return (
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE)
        )
        or 0
    )


@pytest.fixture
def admin(db: Session) -> User:
    return make_user(db, role=UserRole.ADMIN)


def test_approve_a_pending_user(db: Session, admin: User) -> None:
    pending = make_user(db, status=UserStatus.PENDING)

    user = service.approve(db, admin, pending.id, now=NOW)

    assert user.status == UserStatus.ACTIVE
    assert (user.approved_by, user.approved_at) == (admin.id, NOW)


def test_approve_re_enables_a_disabled_user(db: Session, admin: User) -> None:
    disabled = make_user(db, status=UserStatus.DISABLED)

    assert service.approve(db, admin, disabled.id).status == UserStatus.ACTIVE


def test_approve_an_active_user_is_refused(db: Session, admin: User) -> None:
    with pytest.raises(service.AdminActionError, match="already active"):
        service.approve(db, admin, make_user(db).id)


def test_unknown_user(db: Session, admin: User) -> None:
    with pytest.raises(service.UserNotFoundError):
        service.approve(db, admin, uuid.uuid4())


def test_disable_revokes_every_session(db: Session, admin: User) -> None:
    user = make_user(db)
    for _ in range(2):  # phone and laptop
        start_session(db, user.id, LIFETIMES)

    service.disable(db, admin, user.id, now=NOW)

    db.expire_all()
    revoked = db.scalars(select(RefreshToken.revoked_at).where(RefreshToken.user_id == user.id))
    assert list(revoked) == [NOW, NOW]
    assert db.get(User, user.id).status == UserStatus.DISABLED


def test_disable_the_last_admin_is_refused(db: Session, admin: User) -> None:
    with pytest.raises(service.LastAdminError):
        service.disable(db, admin, admin.id)

    assert active_admin_count(db) == 1


def test_demote_the_last_admin_is_refused(db: Session, admin: User) -> None:
    with pytest.raises(service.LastAdminError):
        service.set_role(db, admin, admin.id, UserRole.USER)

    assert active_admin_count(db) == 1


def test_a_disabled_admin_does_not_count(db: Session, admin: User) -> None:
    """Only active administrators keep the site administrable."""
    make_user(db, status=UserStatus.DISABLED, role=UserRole.ADMIN)

    with pytest.raises(service.LastAdminError):
        service.set_role(db, admin, admin.id, UserRole.USER)


def test_with_two_admins_one_can_step_down(db: Session, admin: User) -> None:
    make_user(db, role=UserRole.ADMIN)

    assert service.set_role(db, admin, admin.id, UserRole.USER).role == UserRole.USER
    assert active_admin_count(db) == 1


def test_promote_an_active_user(db: Session, admin: User) -> None:
    user = make_user(db)

    assert service.set_role(db, admin, user.id, UserRole.ADMIN).role == UserRole.ADMIN


@pytest.mark.parametrize("status", [UserStatus.PENDING, UserStatus.DISABLED])
def test_only_active_users_can_become_admins(db: Session, admin: User, status: str) -> None:
    with pytest.raises(service.AdminActionError, match="only active users"):
        service.set_role(db, admin, make_user(db, status=status).id, UserRole.ADMIN)


def test_list_users_by_status(db: Session, admin: User) -> None:
    pending = make_user(db, status=UserStatus.PENDING)

    assert [u.id for u in service.list_users(db, UserStatus.PENDING)] == [pending.id]
    assert {u.id for u in service.list_users(db)} == {admin.id, pending.id}


def concurrently(engine: Engine, *actions: object) -> list[str]:
    """Run each action in its own thread and database session, at the same moment."""
    barrier = threading.Barrier(len(actions))
    outcomes: list[str] = []

    def run(action: object) -> None:
        with Session(engine) as db:
            barrier.wait()
            try:
                action(db)  # type: ignore[operator]
                outcomes.append("done")
            except service.LastAdminError:
                outcomes.append("last-admin")

    threads = [threading.Thread(target=run, args=(action,)) for action in actions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return sorted(outcomes)


def test_two_admins_demoting_each_other_keep_one(migrated_database: Engine, db: Session) -> None:
    """Without the row locks both demotions would see two admins and succeed."""
    # Plain ids: each thread loads the acting admin in its own session (a Session,
    # and the objects attached to it, must not be shared between threads)
    a = make_user(db, role=UserRole.ADMIN).id
    b = make_user(db, role=UserRole.ADMIN).id

    outcomes = concurrently(
        migrated_database,
        lambda s: service.set_role(s, s.get(User, a), b, UserRole.USER),
        lambda s: service.set_role(s, s.get(User, b), a, UserRole.USER),
    )

    assert outcomes == ["done", "last-admin"]
    assert active_admin_count(db) == 1


def test_two_admins_disabling_each_other_keep_one(migrated_database: Engine, db: Session) -> None:
    a = make_user(db, role=UserRole.ADMIN).id
    b = make_user(db, role=UserRole.ADMIN).id

    outcomes = concurrently(
        migrated_database,
        lambda s: service.disable(s, s.get(User, a), b),
        lambda s: service.disable(s, s.get(User, b), a),
    )

    assert outcomes == ["done", "last-admin"]
    assert active_admin_count(db) == 1
