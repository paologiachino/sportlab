"""The two database roles keep data and schema apart.

DATABASE_MIGRATION_URL uses the migration role, which owns the schema;
DATABASE_URL uses the application role, which may only read and write data.
Locally the roles come from docker/dev/postgres-init/20_sportlab.sh through the
development Compose; CI runs the same script on its PostgreSQL service.

Each test creates its own table as the migration role (as a migration would)
and drops it at the end, so the database is left as it was.
"""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from tests.support import require_database, skip_or_fail


@pytest.fixture(scope="module")
def engines() -> Iterator[tuple[Engine, Engine]]:
    """(application engine, migration engine), each with its own role."""
    settings = get_settings()
    app = create_engine(settings.database_url.unicode_string(), poolclass=NullPool)
    migrator = create_engine(settings.database_migration_url.unicode_string(), poolclass=NullPool)
    require_database(app)
    require_database(migrator)

    if app.url.username == migrator.url.username:
        skip_or_fail("DATABASE_URL and DATABASE_MIGRATION_URL use the same role")

    yield app, migrator
    app.dispose()
    migrator.dispose()


@pytest.fixture
def probe_table(engines: tuple[Engine, Engine]) -> Iterator[str]:
    """A table created by the migration role, dropped after the test."""
    _, migrator = engines
    name = f"probe_{uuid.uuid4().hex[:12]}"
    with migrator.begin() as connection:
        connection.execute(text(f"CREATE TABLE {name} (id serial PRIMARY KEY, note text)"))
    try:
        yield name
    finally:
        with migrator.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS {name}"))


def is_superuser(connection: Connection) -> bool:
    return connection.execute(
        text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    ).scalar_one()


def test_neither_role_is_superuser(engines: tuple[Engine, Engine]) -> None:
    for engine in engines:
        with engine.connect() as connection:
            assert not is_superuser(connection), f"{engine.url.username} is a superuser"


def test_application_role_reads_and_writes_data(
    engines: tuple[Engine, Engine], probe_table: str
) -> None:
    """Default privileges: no GRANT is needed for tables the migrator creates."""
    app, _ = engines
    with app.begin() as connection:
        # INSERT also uses the table's sequence (serial)
        connection.execute(text(f"INSERT INTO {probe_table} (note) VALUES ('synthetic')"))
        connection.execute(text(f"UPDATE {probe_table} SET note = 'changed'"))
        assert connection.execute(text(f"SELECT note FROM {probe_table}")).scalar_one() == (
            "changed"
        )
        connection.execute(text(f"DELETE FROM {probe_table}"))


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE {table}_new (id int)",
        "DROP TABLE {table}",
        "ALTER TABLE {table} ADD COLUMN extra int",
        "TRUNCATE {table}",
    ],
)
def test_application_role_cannot_change_the_schema(
    engines: tuple[Engine, Engine], probe_table: str, statement: str
) -> None:
    app, _ = engines
    # Never committed: DDL is transactional in PostgreSQL, so if a statement is
    # wrongly allowed the test fails without leaving anything behind.
    with app.connect() as connection:
        with pytest.raises(ProgrammingError, match="permission denied|must be owner"):
            connection.execute(text(statement.format(table=probe_table)))
        connection.rollback()
