"""User administration through the API: who may call it and what it answers."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.main import app
from app.models import User, UserRole, UserStatus
from tests.support import make_user, sign_in

CSRF = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def db(migrated_database: Engine) -> Iterator[Session]:
    with Session(migrated_database) as session:
        yield session


@pytest.fixture
def client(migrated_database: Engine) -> Iterator[TestClient]:
    def session() -> Iterator[Session]:
        with Session(migrated_database) as s:
            yield s

    app.dependency_overrides[get_db] = session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def admin(client: TestClient, db: Session, settings: Settings) -> User:
    """An active admin, signed in on `client`."""
    user = make_user(db, role=UserRole.ADMIN)
    sign_in(client, db, user, settings)
    return user


def test_list_users_and_filter_by_status(client: TestClient, db: Session, admin: User) -> None:
    pending = make_user(db, status=UserStatus.PENDING)

    everyone = client.get("/api/admin/users")
    only_pending = client.get("/api/admin/users", params={"status": "pending"})

    assert everyone.status_code == 200
    assert {u["id"] for u in everyone.json()} == {str(admin.id), str(pending.id)}
    assert [u["id"] for u in only_pending.json()] == [str(pending.id)]
    assert set(only_pending.json()[0]) == {
        "id", "email", "display_name", "status", "role",
        "created_at", "last_login_at", "approved_at", "approved_by",
    }  # fmt: skip


def test_unknown_status_filter_is_422(client: TestClient, admin: User) -> None:
    assert client.get("/api/admin/users", params={"status": "approved"}).status_code == 422


def test_approve(client: TestClient, db: Session, admin: User) -> None:
    pending = make_user(db, status=UserStatus.PENDING)

    response = client.post(f"/api/admin/users/{pending.id}/approve", headers=CSRF)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "active"
    assert body["approved_by"] == str(admin.id)
    assert body["approved_at"] is not None


def test_disable_signs_the_user_out(
    client: TestClient, db: Session, admin: User, settings: Settings
) -> None:
    user = make_user(db)
    their_client = TestClient(app)
    sign_in(their_client, db, user, settings)
    assert their_client.get("/api/auth/me").status_code == 200

    response = client.post(f"/api/admin/users/{user.id}/disable", headers=CSRF)

    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    # Their refresh token was revoked: the session cannot be renewed
    assert their_client.post("/api/auth/refresh", headers=CSRF).status_code == 401


def test_promote_and_demote(client: TestClient, db: Session, admin: User) -> None:
    user = make_user(db)
    url = f"/api/admin/users/{user.id}/role"

    assert client.post(url, json={"role": "admin"}, headers=CSRF).json()["role"] == "admin"
    assert client.post(url, json={"role": "user"}, headers=CSRF).json()["role"] == "user"


def test_invalid_role_is_422(client: TestClient, db: Session, admin: User) -> None:
    user = make_user(db)

    response = client.post(
        f"/api/admin/users/{user.id}/role", json={"role": "superuser"}, headers=CSRF
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("path", "body"),
    [("disable", None), ("role", {"role": "user"})],
)
def test_last_admin_cannot_be_removed(
    client: TestClient, admin: User, path: str, body: dict[str, str] | None
) -> None:
    response = client.post(f"/api/admin/users/{admin.id}/{path}", json=body, headers=CSRF)

    assert response.status_code == 409
    assert "last active administrator" in response.json()["detail"]
    assert client.get("/api/auth/me").json()["role"] == "admin"


def test_conflicting_state_is_409(client: TestClient, db: Session, admin: User) -> None:
    active = make_user(db)

    response = client.post(f"/api/admin/users/{active.id}/approve", headers=CSRF)

    assert response.status_code == 409
    assert response.json() == {"detail": "the user is already active"}


def test_unknown_user_is_404(client: TestClient, admin: User) -> None:
    response = client.post(f"/api/admin/users/{uuid.uuid4()}/approve", headers=CSRF)

    assert response.status_code == 404


def test_malformed_user_id_is_422(client: TestClient, admin: User) -> None:
    assert client.post("/api/admin/users/not-a-uuid/approve", headers=CSRF).status_code == 422


@pytest.mark.parametrize(
    ("status", "role"),
    [
        (UserStatus.ACTIVE, UserRole.USER),
        (UserStatus.PENDING, UserRole.USER),
        (UserStatus.DISABLED, UserRole.ADMIN),
    ],
)
def test_only_active_admins_may_administer(
    client: TestClient, db: Session, settings: Settings, status: str, role: str
) -> None:
    sign_in(client, db, make_user(db, status=status, role=role), settings)
    target = make_user(db, status=UserStatus.PENDING)

    assert client.get("/api/admin/users").status_code == 403
    assert client.post(f"/api/admin/users/{target.id}/approve", headers=CSRF).status_code == 403


def test_not_signed_in_is_401(client: TestClient) -> None:
    assert client.get("/api/admin/users").status_code == 401


def test_actions_need_the_csrf_header(client: TestClient, db: Session, admin: User) -> None:
    pending = make_user(db, status=UserStatus.PENDING)

    assert client.post(f"/api/admin/users/{pending.id}/approve").status_code == 403
    db.expire_all()
    assert db.get(User, pending.id).status == UserStatus.PENDING
