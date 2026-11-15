"""Declarative base for the SQLAlchemy models, and the metadata Alembic compares against."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Explicit, predictable constraint names. Without them PostgreSQL picks the names,
# and a later migration that drops or alters a constraint cannot refer to it
# reliably (downgrades in particular).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class of every model (see app/models)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Tables created by PostgreSQL extensions, not by our migrations: PostGIS keeps
# its coordinate systems in spatial_ref_sys. Alembic must neither create nor
# drop them when comparing the models with the database.
EXTENSION_TABLES = frozenset({"spatial_ref_sys"})


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Alembic filter: skip the tables that belong to extensions."""
    return not (type_ == "table" and reflected and name in EXTENSION_TABLES)
