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
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from tests.support import require_database

SYNTHETIC_ENV = {
    "ENVIRONMENT": "development",
    "DATABASE_URL": "postgresql+psycopg://test_app:test@localhost:5432/sportlab_test",
    "DATABASE_MIGRATION_URL": "postgresql+psycopg://test_migrator:test@localhost:5432/sportlab_test",
    "SECRET_KEY": "test-" + "x" * 32,  # obviously fake, long enough for the check
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
        # Nested so the DROP runs even if closing the test's connections fails;
        # any error is still reported, but no database is left behind
        try:
            engine.dispose()
        finally:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            admin.dispose()


@pytest.fixture
def migrated_database(empty_database: Engine) -> Engine:
    """A brand new database with every migration applied (`alembic upgrade head`).

    The schema comes from the migrations, as in production, not from
    `Base.metadata.create_all()`.
    """
    from alembic import command
    from alembic.config import Config

    config = Config(Path(__file__).resolve().parents[1] / "alembic.ini")
    with empty_database.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return empty_database
