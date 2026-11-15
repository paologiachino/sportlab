"""Shared test setup.

pytest loads this file before importing the test modules, so the environment
below is in place when `app.main` validates the settings. For each variable,
the first source that has it wins:

1. the process environment (for example CI);
2. the repository's .env (locally, with the development Compose database);
3. the synthetic values below.
"""

import os
import uuid
from collections.abc import Iterator

import pytest
from dotenv import dotenv_values
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

SYNTHETIC_ENV = {
    "ENVIRONMENT": "development",
    "DATABASE_URL": "postgresql+psycopg://test_app:test@localhost:5432/sportlab_test",
    "DATABASE_MIGRATION_URL": "postgresql+psycopg://test_migrator:test@localhost:5432/sportlab_test",
    "SECRET_KEY": "test-secret-key",
    "ENCRYPTION_KEY": "test-encryption-key",
}


def _prepare_environment() -> None:
    # Imported here: importing app.core.config does not read any setting yet
    from app.core.config import ENV_FILE

    # Same ${...} expansion as the backend and Docker Compose
    for name, value in dotenv_values(ENV_FILE).items():
        if value:
            os.environ.setdefault(name, value)
    for name, value in SYNTHETIC_ENV.items():
        os.environ.setdefault(name, value)


_prepare_environment()


def require_database(engine: Engine) -> None:
    """Stop the test when the database behind `engine` is not reachable.

    Locally the test is skipped, but in CI it fails: there a skip would hide a
    broken setup behind a green run.
    """
    try:
        with engine.connect():
            pass
    except OperationalError:
        if os.environ.get("CI"):
            pytest.fail("Test database not reachable in CI: check the postgres service")
        pytest.skip("Test database not reachable (start the development database)")


@pytest.fixture
def db_session() -> Iterator[Session]:
    """A session on the real test database (DATABASE_URL)."""
    # Imported here, after the synthetic environment above is in place
    from app.db.session import SessionLocal, engine

    require_database(engine)
    with SessionLocal() as session:
        yield session


@pytest.fixture
def empty_database() -> Iterator[Engine]:
    """A brand new, empty database for the test, dropped afterwards.

    Created with the migration role (DATABASE_MIGRATION_URL), which needs the
    CREATEDB privilege: true for the CI service and the development database.
    """
    from app.core.config import get_settings

    server_url = make_url(get_settings().database_migration_url.unicode_string())
    # CREATE/DROP DATABASE cannot run inside a transaction, hence AUTOCOMMIT.
    # They connect to the "postgres" maintenance database of the same server.
    admin = create_engine(
        server_url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    require_database(admin)

    name = f"sportlab_test_{uuid.uuid4().hex[:12]}"
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))

    engine = create_engine(server_url.set(database=name), poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
