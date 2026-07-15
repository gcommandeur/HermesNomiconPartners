"""add mailing_groups table

Revision ID: d5f8e3a7b1c9
Revises: c4e7a1d9f2b6
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5f8e3a7b1c9"
down_revision: str | None = "c4e7a1d9f2b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mailing_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("recipients", sa.JSON(), nullable=False),
        sa.Column("template_key", sa.String(length=80), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mailing_groups_name", "mailing_groups", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_mailing_groups_name", table_name="mailing_groups")
    op.drop_table("mailing_groups")
