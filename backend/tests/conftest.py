"""Shared test setup.

pytest loads this file before importing the test modules, so the synthetic
environment below is in place when `app.main` validates the settings.
Values already set (for example by CI) are kept.
"""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

SYNTHETIC_ENV = {
    "ENVIRONMENT": "development",
    "DATABASE_URL": "postgresql+psycopg://test_app:test@localhost:5432/sportlab_test",
    "DATABASE_MIGRATION_URL": "postgresql+psycopg://test_migrator:test@localhost:5432/sportlab_test",
    "SECRET_KEY": "test-secret-key",
    "ENCRYPTION_KEY": "test-encryption-key",
}

for name, value in SYNTHETIC_ENV.items():
    os.environ.setdefault(name, value)


@pytest.fixture
def db_session() -> Iterator[Session]:
    """A session on the real test database (DATABASE_URL).

    Without a reachable database the test is skipped locally, but fails in CI:
    there a skip would hide a broken setup behind a green run.
    """
    # Imported here, after the synthetic environment above is in place
    from app.db.session import SessionLocal, engine

    try:
        with engine.connect():
            pass
    except OperationalError:
        if os.environ.get("CI"):
            pytest.fail("Test database not reachable in CI: check the postgres service")
        pytest.skip("Test database not reachable (start the development database)")

    with SessionLocal() as session:
        yield session
