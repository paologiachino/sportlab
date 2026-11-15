"""Refresh token sessions: rotation, sliding and absolute expiry, reuse, logout."""

import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.core.security import hash_refresh_token
from app.models import RefreshToken, User
from app.services.sessions import (
    InvalidRefreshTokenError,
    RefreshTokenReuseError,
    SessionLifetimes,
    end_all_sessions,
    end_session,
    rotate,
    start_session,
)

LIFETIMES = SessionLifetimes(refresh=timedelta(days=30), session=timedelta(days=90))
T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def days(n: float) -> datetime:
    return T0 + timedelta(days=n)


@pytest.fixture
def db(migrated_database: Engine) -> Iterator[Session]:
    with Session(migrated_database) as session:
        yield session


def make_user(db: Session) -> uuid.UUID:
    sub = uuid.uuid4().hex
    user = User(google_sub=sub, email=f"user-{sub[:8]}@example.com")
    db.add(user)
    db.commit()
    return user.id


@pytest.fixture
def user_id(db: Session) -> uuid.UUID:
    return make_user(db)


def tokens_of(db: Session, session_id: uuid.UUID) -> list[RefreshToken]:
    db.expire_all()
    return list(db.scalars(select(RefreshToken).where(RefreshToken.session_id == session_id)))


def test_start_session_stores_only_the_hash(db: Session, user_id: uuid.UUID) -> None:
    issued = start_session(db, user_id, LIFETIMES, now=T0)

    [row] = tokens_of(db, issued.session_id)
    assert row.token_hash == hash_refresh_token(issued.token)
    assert issued.token not in {row.token_hash, str(row.id)}
    assert row.expires_at == days(30)
    assert row.session_expires_at == days(90)
    assert row.revoked_at is None


def test_rotation_replaces_the_token_in_the_same_session(db: Session, user_id: uuid.UUID) -> None:
    first = start_session(db, user_id, LIFETIMES, now=T0)
    second = rotate(db, first.token, LIFETIMES, now=days(1))

    assert second.token != first.token
    assert second.session_id == first.session_id
    assert second.user_id == user_id
    assert second.expires_at == days(31)  # sliding
    rows = {row.token_hash: row for row in tokens_of(db, first.session_id)}
    assert rows[hash_refresh_token(first.token)].revoked_at == days(1)
    assert rows[hash_refresh_token(second.token)].revoked_at is None


def test_reuse_of_a_rotated_token_revokes_the_session(db: Session, user_id: uuid.UUID) -> None:
    first = start_session(db, user_id, LIFETIMES, now=T0)
    second = rotate(db, first.token, LIFETIMES, now=days(1))

    # Someone presents the old token again: it was copied
    with pytest.raises(RefreshTokenReuseError):
        rotate(db, first.token, LIFETIMES, now=days(2))

    assert all(row.revoked_at is not None for row in tokens_of(db, first.session_id))
    # The latest token is gone too, for whoever holds it
    with pytest.raises(InvalidRefreshTokenError):
        rotate(db, second.token, LIFETIMES, now=days(2))


def test_unknown_token_is_refused(db: Session) -> None:
    with pytest.raises(InvalidRefreshTokenError) as error:
        rotate(db, "not-a-real-token", LIFETIMES, now=T0)

    assert not isinstance(error.value, RefreshTokenReuseError)


def test_inactive_for_longer_than_the_refresh_lifetime(db: Session, user_id: uuid.UUID) -> None:
    first = start_session(db, user_id, LIFETIMES, now=T0)

    with pytest.raises(InvalidRefreshTokenError, match="expired"):
        rotate(db, first.token, LIFETIMES, now=days(31))


def test_regular_use_slides_until_the_absolute_limit(db: Session, user_id: uuid.UUID) -> None:
    token = start_session(db, user_id, LIFETIMES, now=T0).token

    # Used every 29 days: each rotation extends the token...
    for day in (29, 58, 87):
        issued = rotate(db, token, LIFETIMES, now=days(day))
        token = issued.token

    # ...but never beyond 90 days from the Google login
    assert issued.expires_at == days(90)
    with pytest.raises(InvalidRefreshTokenError, match="expired"):
        rotate(db, token, LIFETIMES, now=days(90))


def test_logout_revokes_the_session(db: Session, user_id: uuid.UUID) -> None:
    first = start_session(db, user_id, LIFETIMES, now=T0)
    second = rotate(db, first.token, LIFETIMES, now=days(1))

    end_session(db, second.token, now=days(2))

    assert all(row.revoked_at is not None for row in tokens_of(db, first.session_id))
    with pytest.raises(InvalidRefreshTokenError):
        rotate(db, second.token, LIFETIMES, now=days(3))


def test_logout_with_an_unknown_token_does_nothing(db: Session) -> None:
    end_session(db, "not-a-real-token", now=T0)


def test_end_all_sessions_spares_other_users(db: Session, user_id: uuid.UUID) -> None:
    other_user = make_user(db)
    phone = start_session(db, user_id, LIFETIMES, now=T0)
    laptop = start_session(db, user_id, LIFETIMES, now=T0)
    other = start_session(db, other_user, LIFETIMES, now=T0)

    end_all_sessions(db, user_id, now=days(1))

    for issued in (phone, laptop):
        with pytest.raises(InvalidRefreshTokenError):
            rotate(db, issued.token, LIFETIMES, now=days(2))
    assert rotate(db, other.token, LIFETIMES, now=days(2)).user_id == other_user


def test_deleting_a_user_deletes_their_tokens(db: Session, user_id: uuid.UUID) -> None:
    issued = start_session(db, user_id, LIFETIMES, now=T0)

    db.execute(delete(User).where(User.id == user_id))
    db.commit()

    assert tokens_of(db, issued.session_id) == []


def test_concurrent_rotations_of_one_token(migrated_database: Engine, user_id: uuid.UUID) -> None:
    """Two requests with the same token at the same moment: the row lock serialises
    them, so exactly one gets a new token and the other is treated as a reuse.

    The frontend must therefore refresh once at a time (one request shared by
    every tab), or the session ends.
    """
    with Session(migrated_database) as db:
        token = start_session(db, user_id, LIFETIMES, now=T0).token

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def attempt() -> None:
        with Session(migrated_database) as db:
            barrier.wait()
            try:
                rotate(db, token, LIFETIMES, now=days(1))
                outcomes.append("rotated")
            except RefreshTokenReuseError:
                outcomes.append("reuse")

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcomes) == ["reuse", "rotated"]
