"""initial empty revision

Intentionally empty: it creates the `alembic_version` table and gives every
database (development, staging, production) a common starting point, so the
first real schema change arrives as an ordinary, reviewable revision.

Revision ID: 42e4b52a9634
Revises:
Create Date: 2026-11-15 10:51:42.586382

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "42e4b52a9634"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
