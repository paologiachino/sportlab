"""create users table

Users who sign in with Google: identity (google_sub), approval status and role.
Reviewed by hand: autogenerate also proposed dropping PostGIS's spatial_ref_sys,
which is not ours; extension tables are now ignored in migrations/env.py.

Revision ID: 3a216fe10f3b
Revises: 42e4b52a9634
Create Date: 2026-11-15 16:23:14.990624

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a216fe10f3b"
down_revision: str | Sequence[str] | None = "42e4b52a9634"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("google_sub", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("role", sa.String(length=16), server_default="user", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint("role IN ('user', 'admin')", name=op.f("ck_users_role")),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'disabled')", name=op.f("ck_users_status")
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name=op.f("fk_users_approved_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("google_sub", name=op.f("uq_users_google_sub")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("users")
