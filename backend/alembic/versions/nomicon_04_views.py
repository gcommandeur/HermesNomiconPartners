"""NOMICON: Ansichten (user_view_access, user_view_settings)

Revision ID: nomicon04views
Revises: nomicon03commission
Create Date: 2026-10-14

Nur in der Nomicon-Kopie (siehe KOPIE.md). Datenmigration: bestehende aktive Nutzer bekommen
die Ansicht "direct", Admins zusaetzlich "staffing" und "management".
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "nomicon04views"
down_revision: str | None = "nomicon03commission"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    """Apply this migration."""
    access = op.create_table(
        "user_view_access",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("view", sa.String(length=20), nullable=False),
        sa.Column("granted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_view_access_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"],
            ["users.id"],
            name=op.f("fk_user_view_access_granted_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_view_access")),
        sa.UniqueConstraint("user_id", "view", name=op.f("uq_user_view_access_user_id")),
    )
    op.create_index(op.f("ix_user_view_access_user_id"), "user_view_access", ["user_id"])
    op.create_table(
        "user_view_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("default_view", sa.String(length=20), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_view_settings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_view_settings")),
        sa.UniqueConstraint("user_id", name=op.f("uq_user_view_settings_user_id")),
    )

    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("role", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    rows = op.get_bind().execute(
        sa.select(users.c.id, users.c.role).where(users.c.is_active.is_(True))
    )
    values = []
    for user_id, role in rows:
        views = ["direct", "staffing", "management"] if role == "admin" else ["direct"]
        values.extend({"id": uuid.uuid4(), "user_id": user_id, "view": view} for view in views)
    if values:
        op.bulk_insert(access, values)


def downgrade() -> None:
    """Revert this migration."""
    op.drop_table("user_view_settings")
    op.drop_index(op.f("ix_user_view_access_user_id"), table_name="user_view_access")
    op.drop_table("user_view_access")
