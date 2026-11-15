"""Alembic environment: how migrations connect to the database.

The URL comes from DATABASE_MIGRATION_URL (the migration role, which owns the
schema), never from alembic.ini. Tests can pass an open connection instead,
through `config.attributes["connection"]`.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool

from app.core.config import get_settings
from app.db.base import Base

config = context.config

# Logging from alembic.ini only when run from the command line: inside the tests
# it would reconfigure (and by default disable) the application's loggers.
if config.config_file_name is not None and "connection" not in config.attributes:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The models' metadata, compared with the database by `alembic revision --autogenerate`
target_metadata = Base.metadata


def migration_url() -> str:
    return get_settings().database_migration_url.unicode_string()


def run_migrations_offline() -> None:
    """Write the SQL instead of running it (`alembic upgrade head --sql`), for review."""
    context.configure(
        url=migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_on(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        run_migrations_on(connection)
        return

    # NullPool: a migration is a one-off command, no connection pool needed
    engine = create_engine(migration_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        run_migrations_on(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
