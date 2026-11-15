"""Alembic migrations: one head, and every revision upgrades and downgrades cleanly."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect

from app.db.base import include_object
from app.models import Base

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture
def alembic_config() -> Config:
    return Config(ALEMBIC_INI)


def run(config: Config, engine: Engine, action: str, revision: str) -> None:
    """Run `alembic upgrade|downgrade <revision>` on `engine`, in one transaction."""
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        getattr(command, action)(config, revision)


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def revisions_from_base(config: Config) -> list[str]:
    """Revision ids in the order they apply, oldest first."""
    script = ScriptDirectory.from_config(config)
    return [rev.revision for rev in reversed(list(script.walk_revisions()))]


def test_single_head(alembic_config: Config) -> None:
    heads = ScriptDirectory.from_config(alembic_config).get_heads()

    assert len(heads) == 1, f"Several heads, merge them with `alembic merge`: {heads}"


def test_upgrade_head_then_downgrade_base(alembic_config: Config, empty_database: Engine) -> None:
    head = ScriptDirectory.from_config(alembic_config).get_current_head()

    run(alembic_config, empty_database, "upgrade", "head")
    assert current_revision(empty_database) == head

    run(alembic_config, empty_database, "downgrade", "base")
    assert current_revision(empty_database) is None
    # Nothing left behind but Alembic's own bookkeeping table
    assert set(inspect(empty_database).get_table_names()) <= {"alembic_version"}


def test_every_revision_downgrades_and_upgrades_again(
    alembic_config: Config, empty_database: Engine
) -> None:
    """Stairway test: up one step, down one step, up again, for every revision.

    It catches a downgrade() that does not undo its upgrade(), which a single
    upgrade head / downgrade base can miss.
    """
    for revision in revisions_from_base(alembic_config):
        run(alembic_config, empty_database, "upgrade", revision)
        run(alembic_config, empty_database, "downgrade", "-1")
        run(alembic_config, empty_database, "upgrade", revision)
        assert current_revision(empty_database) == revision


def test_models_match_migrations(alembic_config: Config, empty_database: Engine) -> None:
    """After `upgrade head` the schema equals the models: no model change lacks a migration."""
    run(alembic_config, empty_database, "upgrade", "head")

    with empty_database.connect() as connection:
        context = MigrationContext.configure(connection, opts={"include_object": include_object})
        differences = compare_metadata(context, Base.metadata)

    assert not differences, f"Models and migrations differ, add a revision: {differences}"
