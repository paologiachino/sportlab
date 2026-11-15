"""Google sign-in through the API, against the fake Google in fake_google.py."""

import logging
from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.google import build_google_client, get_google_client
from app.core.security import decode_access_token, hash_refresh_token
from app.db.session import get_db
from app.main import app
from app.models import RefreshToken, User, UserRole, UserStatus
from tests.fake_google import Account, FakeGoogle, new_rsa_key

CLIENT_ID = "fake-client-id.apps.googleusercontent.com"
CLIENT_SECRET = "fake-client-secret"  # noqa: S105 (synthetic)
ADMIN_EMAIL = "admin@example.com"


@pytest.fixture
def settings() -> Settings:
    return get_settings().model_copy(
        update={
            "google_client_id": CLIENT_ID,
            "google_client_secret": SecretStr(CLIENT_SECRET),
            "admin_email": ADMIN_EMAIL,
        }
    )


@pytest.fixture
def google(settings: Settings) -> FakeGoogle:
    return FakeGoogle(CLIENT_ID, CLIENT_SECRET)


@pytest.fixture
def client(
    migrated_database: Engine, settings: Settings, google: FakeGoogle
) -> Iterator[TestClient]:
    def db() -> Iterator[Session]:
        with Session(migrated_database) as session:
            yield session

    google_client = build_google_client(settings, transport=google.transport)
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_google_client] = lambda: google_client
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def db(migrated_database: Engine) -> Iterator[Session]:
    with Session(migrated_database) as session:
        yield session


def start_login(client: TestClient) -> dict[str, str]:
    """GET /login and return the query of the redirect to Google."""
    response = client.get("/api/auth/google/login", follow_redirects=False)
    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == (
        "https://accounts.google.com/o/oauth2/v2/auth"
    )
    return {key: values[0] for key, values in parse_qs(location.query).items()}


def sign_in(
    client: TestClient, google: FakeGoogle, account: Account, **claim_overrides: object
) -> object:
    """The whole round trip: /login, the person approves at Google, /callback."""
    query = start_login(client)
    # The nonce Google echoes back is the one from /login, unless a test forges it
    nonce = str(claim_overrides.pop("nonce", query["nonce"]))
    code = google.issue_code(account, nonce=nonce, **claim_overrides)
    return client.get(
        "/api/auth/google/callback",
        params={"code": code, "state": query["state"]},
        follow_redirects=False,
    )


def count_users(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0


def test_login_redirects_to_google_with_state_nonce_and_pkce(client: TestClient) -> None:
    query = start_login(client)

    assert query["client_id"] == CLIENT_ID
    assert query["redirect_uri"] == "http://localhost:8000/api/auth/google/callback"
    assert query["response_type"] == "code"
    assert set(query["scope"].split()) == {"openid", "email", "profile"}
    assert query["code_challenge_method"] == "S256"
    for name in ("state", "nonce", "code_challenge"):
        assert len(query[name]) >= 20
    assert "sportlab_oauth" in client.cookies


def test_new_user_is_pending_and_gets_a_session(
    client: TestClient, google: FakeGoogle, db: Session, settings: Settings
) -> None:
    account = Account(email="New.Person@Example.com")

    response = sign_in(client, google, account)

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    user = db.scalars(select(User).where(User.google_sub == account.sub)).one()
    assert user.status == UserStatus.PENDING
    assert user.role == UserRole.USER
    assert user.email == "new.person@example.com"
    assert user.last_login_at is not None

    # The access cookie names this user; the refresh cookie matches a stored hash
    access = client.cookies["sportlab_access"]
    assert decode_access_token(access, settings.secret_key.get_secret_value()) == user.id
    refresh_hash = hash_refresh_token(client.cookies["sportlab_refresh"])
    assert db.scalars(select(RefreshToken).where(RefreshToken.token_hash == refresh_hash)).one()

    # The token exchange carried the PKCE verifier (the fake refuses it otherwise)
    assert google.token_requests[-1]["code_verifier"]


def test_session_cookies_are_httponly_and_strict(client: TestClient, google: FakeGoogle) -> None:
    response = sign_in(client, google, Account())

    cookies = response.headers.get_list("set-cookie")
    access = next(c for c in cookies if c.startswith("sportlab_access="))
    refresh = next(c for c in cookies if c.startswith("sportlab_refresh="))
    for cookie in (access, refresh):
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
    assert "Path=/;" in access or access.endswith("Path=/")
    assert "Path=/api/auth" in refresh


def test_admin_email_creates_an_active_admin(
    client: TestClient, google: FakeGoogle, db: Session
) -> None:
    account = Account(email="ADMIN@example.com")

    assert sign_in(client, google, account).status_code == 303

    user = db.scalars(select(User).where(User.google_sub == account.sub)).one()
    assert (user.status, user.role) == (UserStatus.ACTIVE, UserRole.ADMIN)


def test_sign_in_never_changes_status_or_role(
    client: TestClient, google: FakeGoogle, db: Session
) -> None:
    """An admin demoted by another admin does not become admin again by signing in."""
    account = Account(email=ADMIN_EMAIL)
    db.add(
        User(
            google_sub=account.sub,
            email="old-address@example.com",
            status=UserStatus.ACTIVE,
            role=UserRole.USER,
        )
    )
    db.commit()

    assert sign_in(client, google, account).status_code == 303

    db.expire_all()
    user = db.scalars(select(User).where(User.google_sub == account.sub)).one()
    assert (user.status, user.role) == (UserStatus.ACTIVE, UserRole.USER)
    assert user.email == ADMIN_EMAIL  # what Google says now
    assert count_users(db) == 1


def test_unverified_email_is_refused(client: TestClient, google: FakeGoogle, db: Session) -> None:
    response = sign_in(client, google, Account(email=ADMIN_EMAIL, email_verified=False))

    assert response.status_code == 403
    assert count_users(db) == 0
    assert "sportlab_access" not in client.cookies


def test_wrong_state_is_refused(client: TestClient, google: FakeGoogle, db: Session) -> None:
    """Login CSRF: a callback that this browser's login did not start."""
    query = start_login(client)
    code = google.issue_code(Account(), nonce=query["nonce"])

    response = client.get(
        "/api/auth/google/callback",
        params={"code": code, "state": "forged-state"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert count_users(db) == 0


@pytest.mark.parametrize(
    "claims",
    [
        {"nonce": "another-nonce"},
        {"aud": "someone-elses-client-id"},
        {"iss": "https://evil.example.com"},
        {"exp": 1_000_000_000},  # long expired
    ],
    ids=["wrong-nonce", "wrong-audience", "wrong-issuer", "expired"],
)
def test_invalid_id_token_is_refused(
    client: TestClient, google: FakeGoogle, db: Session, claims: dict[str, object]
) -> None:
    response = sign_in(client, google, Account(), **claims)

    assert response.status_code == 400
    assert count_users(db) == 0


def test_id_token_signed_by_another_key_is_refused(
    client: TestClient, google: FakeGoogle, db: Session
) -> None:
    query = start_login(client)
    code = google.issue_code(Account(), nonce=query["nonce"], signing_key=new_rsa_key())

    response = client.get(
        "/api/auth/google/callback",
        params={"code": code, "state": query["state"]},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert count_users(db) == 0


def test_callback_cannot_be_replayed(client: TestClient, google: FakeGoogle) -> None:
    query = start_login(client)
    code = google.issue_code(Account(), nonce=query["nonce"])
    params = {"code": code, "state": query["state"]}

    first = client.get("/api/auth/google/callback", params=params, follow_redirects=False)
    second = client.get("/api/auth/google/callback", params=params, follow_redirects=False)

    assert first.status_code == 303
    assert second.status_code == 400


def test_logs_carry_no_email_or_name(
    client: TestClient, google: FakeGoogle, caplog: pytest.LogCaptureFixture
) -> None:
    account = Account(email="private.person@example.com", name="Private Person")

    with caplog.at_level(logging.INFO):
        sign_in(client, google, account)

    assert "New user" in caplog.text
    assert "private.person" not in caplog.text
    assert "Private Person" not in caplog.text


def test_not_configured_answers_503() -> None:
    app.dependency_overrides[get_google_client] = lambda: None
    try:
        client = TestClient(app)
        assert client.get("/api/auth/google/login", follow_redirects=False).status_code == 503
        assert client.get("/api/auth/google/callback").status_code == 503
    finally:
        app.dependency_overrides.clear()
