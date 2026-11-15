"""Session endpoints (/me, /refresh, /logout), access levels and the CSRF header."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.api.deps import ActiveUser, AdminUser
from app.core.config import Settings, get_settings
from app.core.csrf import RequireCSRFHeader
from app.core.security import create_access_token, decode_access_token, hash_refresh_token
from app.db.session import get_db
from app.main import app
from app.models import RefreshToken, UserRole, UserStatus
from tests.support import make_user, set_cookie, sign_in

CSRF = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def db(migrated_database: Engine) -> Iterator[Session]:
    with Session(migrated_database) as session:
        yield session


def override(target: FastAPI, migrated_database: Engine) -> None:
    def session() -> Iterator[Session]:
        with Session(migrated_database) as s:
            yield s

    target.dependency_overrides[get_db] = session


@pytest.fixture
def client(migrated_database: Engine) -> Iterator[TestClient]:
    override(app, migrated_database)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# --- GET /api/auth/me ---------------------------------------------------------


def test_me_returns_only_the_public_fields(
    client: TestClient, db: Session, settings: Settings
) -> None:
    user = make_user(db)
    sign_in(client, db, user, settings)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.id),
        "email": user.email,
        "display_name": None,
        "status": "active",
        "role": "user",
    }


@pytest.mark.parametrize("status", [UserStatus.PENDING, UserStatus.DISABLED])
def test_me_works_for_pending_and_disabled_users(
    client: TestClient, db: Session, settings: Settings, status: str
) -> None:
    """So the interface can say "waiting for approval" or "access removed"."""
    sign_in(client, db, make_user(db, status=status), settings)

    assert client.get("/api/auth/me").json()["status"] == status


def test_me_without_cookie_is_401(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_expired_or_forged_token_is_401(
    client: TestClient, db: Session, settings: Settings
) -> None:
    user = make_user(db)
    expired = create_access_token(
        user.id,
        settings.secret_key.get_secret_value(),
        timedelta(minutes=15),
        now=datetime.now(UTC) - timedelta(hours=1),
    )
    forged = create_access_token(user.id, "f" * 32, timedelta(minutes=15))

    for token in (expired, forged, "garbage"):
        set_cookie(client, "sportlab_access", token)
        assert client.get("/api/auth/me").status_code == 401


def test_me_for_a_deleted_user_is_401(client: TestClient, db: Session, settings: Settings) -> None:
    user = make_user(db)
    sign_in(client, db, user, settings)
    db.delete(user)
    db.commit()

    assert client.get("/api/auth/me").status_code == 401


# --- POST /api/auth/refresh ---------------------------------------------------


def test_refresh_rotates_both_cookies(client: TestClient, db: Session, settings: Settings) -> None:
    user = make_user(db)
    old_refresh = sign_in(client, db, user, settings)

    response = client.post("/api/auth/refresh", headers=CSRF)

    assert response.status_code == 204
    assert client.cookies["sportlab_refresh"] != old_refresh
    # A fresh access token for the same user (a JWT is deterministic, so within the
    # same second it can equal the old one: what matters is that it is valid)
    new_access = client.cookies["sportlab_access"]
    assert decode_access_token(new_access, settings.secret_key.get_secret_value()) == user.id
    assert client.get("/api/auth/me").json()["id"] == str(user.id)


def test_reusing_an_old_refresh_token_ends_the_session(
    client: TestClient, db: Session, settings: Settings
) -> None:
    old_refresh = sign_in(client, db, make_user(db), settings)
    assert client.post("/api/auth/refresh", headers=CSRF).status_code == 204
    new_refresh = client.cookies["sportlab_refresh"]

    # An attacker replays the copied old token
    set_cookie(client, "sportlab_refresh", old_refresh)
    response = client.post("/api/auth/refresh", headers=CSRF)

    assert response.status_code == 401
    # ...and the owner's current token is dead too
    set_cookie(client, "sportlab_refresh", new_refresh)
    assert client.post("/api/auth/refresh", headers=CSRF).status_code == 401


def test_refresh_without_cookie_is_401(client: TestClient) -> None:
    assert client.post("/api/auth/refresh", headers=CSRF).status_code == 401


def test_failed_refresh_clears_the_cookies(client: TestClient) -> None:
    set_cookie(client, "sportlab_refresh", "not-a-real-token")

    response = client.post("/api/auth/refresh", headers=CSRF)

    assert response.status_code == 401
    cleared = response.headers.get_list("set-cookie")
    assert any(c.startswith("sportlab_access=") and "Max-Age=0" in c for c in cleared)
    assert any(c.startswith("sportlab_refresh=") and "Max-Age=0" in c for c in cleared)


# --- POST /api/auth/logout ----------------------------------------------------


def test_logout_revokes_the_session_and_clears_cookies(
    client: TestClient, db: Session, settings: Settings
) -> None:
    refresh = sign_in(client, db, make_user(db), settings)

    response = client.post("/api/auth/logout", headers=CSRF)

    assert response.status_code == 204
    row = db.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh))
    ).one()
    assert row.revoked_at is not None
    assert "sportlab_refresh" not in client.cookies
    set_cookie(client, "sportlab_refresh", refresh)
    assert client.post("/api/auth/refresh", headers=CSRF).status_code == 401


def test_logout_when_signed_out_is_fine(client: TestClient) -> None:
    assert client.post("/api/auth/logout", headers=CSRF).status_code == 204


# --- CSRF header --------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/auth/refresh", "/api/auth/logout"])
def test_state_changing_requests_need_the_csrf_header(
    client: TestClient, db: Session, settings: Settings, path: str
) -> None:
    refresh = sign_in(client, db, make_user(db), settings)

    response = client.post(path)

    assert response.status_code == 403
    assert response.json() == {"detail": "Missing X-Requested-With header"}
    # Refused before reaching the endpoint: the session is untouched
    row = db.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh))
    ).one()
    assert row.revoked_at is None


def test_get_requests_need_no_csrf_header(client: TestClient) -> None:
    assert client.get("/api/health").status_code == 200


# --- Access levels ------------------------------------------------------------


@pytest.fixture
def levels_client(migrated_database: Engine) -> Iterator[TestClient]:
    """A small app with one route per access level, as later endpoints will declare."""
    levels = FastAPI()
    levels.add_middleware(RequireCSRFHeader)

    @levels.get("/api/active")
    def active(user: ActiveUser) -> dict[str, str]:
        return {"id": str(user.id)}

    @levels.get("/api/admin")
    def admin(user: AdminUser) -> dict[str, str]:
        return {"id": str(user.id)}

    override(levels, migrated_database)
    yield TestClient(levels)


@pytest.mark.parametrize(
    ("status", "role", "active_code", "admin_code"),
    [
        (UserStatus.ACTIVE, UserRole.USER, 200, 403),
        (UserStatus.ACTIVE, UserRole.ADMIN, 200, 200),
        (UserStatus.PENDING, UserRole.USER, 403, 403),
        (UserStatus.DISABLED, UserRole.USER, 403, 403),
        (UserStatus.DISABLED, UserRole.ADMIN, 403, 403),  # a disabled admin is no admin
    ],
)
def test_access_levels(
    levels_client: TestClient,
    db: Session,
    settings: Settings,
    status: str,
    role: str,
    active_code: int,
    admin_code: int,
) -> None:
    sign_in(levels_client, db, make_user(db, status=status, role=role), settings)

    assert levels_client.get("/api/active").status_code == active_code
    assert levels_client.get("/api/admin").status_code == admin_code


def test_access_levels_read_the_database_not_the_token(
    levels_client: TestClient, db: Session, settings: Settings
) -> None:
    """An admin demoted after signing in loses access with the same token."""
    admin = make_user(db, role=UserRole.ADMIN)
    sign_in(levels_client, db, admin, settings)
    assert levels_client.get("/api/admin").status_code == 200

    admin.role = UserRole.USER
    db.commit()

    assert levels_client.get("/api/admin").status_code == 403


def test_access_levels_without_cookie_are_401(levels_client: TestClient) -> None:
    assert levels_client.get("/api/active").status_code == 401
    assert levels_client.get("/api/admin").status_code == 401
