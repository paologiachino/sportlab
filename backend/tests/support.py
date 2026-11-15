"""Helpers shared by the tests (imported, unlike the fixtures in conftest.py)."""

import os
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.cookies import REFRESH_COOKIE_PATH
from app.core.security import create_access_token
from app.models import User, UserRole, UserStatus
from app.services.sessions import SessionLifetimes, start_session


def skip_or_fail(reason: str) -> None:
    """Skip the test locally, but fail it in CI.

    In CI a skip would hide a broken setup behind a green run.
    """
    if os.environ.get("CI"):
        pytest.fail(f"{reason} (in CI this must not happen: check the workflow)")
    pytest.skip(reason)


def require_database(engine: Engine) -> None:
    """Stop the test when the database behind `engine` is not reachable."""
    try:
        with engine.connect():
            pass
    except OperationalError:
        skip_or_fail("Test database not reachable (start the development database)")


def make_user(db: Session, status: str = UserStatus.ACTIVE, role: str = UserRole.USER) -> User:
    sub = uuid.uuid4().hex
    user = User(google_sub=sub, email=f"user-{sub[:8]}@example.com", status=status, role=role)
    db.add(user)
    db.commit()
    return user


def sign_in(client: TestClient, db: Session, user: User, settings: Settings) -> str:
    """Put the cookies the Google callback would set; returns the refresh token."""
    issued = start_session(db, user.id, SessionLifetimes.from_settings(settings))
    access = create_access_token(
        user.id, settings.secret_key.get_secret_value(), timedelta(minutes=15)
    )
    set_cookie(client, "sportlab_access", access)
    set_cookie(client, "sportlab_refresh", issued.token)
    return issued.token


# The test client's host; httpx stores cookies of dotless hosts under ".local"
COOKIE_DOMAIN = "testserver.local"
COOKIE_PATHS = {"sportlab_access": "/", "sportlab_refresh": REFRESH_COOKIE_PATH}


def set_cookie(client: TestClient, name: str, value: str) -> None:
    """Set a cookie as the server does (same domain and path), so the server's own
    Set-Cookie replaces it instead of creating a second cookie with the same name."""
    client.cookies.set(name, value, domain=COOKIE_DOMAIN, path=COOKIE_PATHS[name])
