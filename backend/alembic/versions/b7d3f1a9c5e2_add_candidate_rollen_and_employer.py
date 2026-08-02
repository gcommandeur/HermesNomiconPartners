"""add candidate rollen (normalized role list) and current_employer_internal

Revision ID: b7d3f1a9c5e2
Revises: a3c8e1f6b2d9
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7d3f1a9c5e2"
down_revision: str | None = "a3c8e1f6b2d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column("rollen", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "candidates",
        sa.Column("current_employer_internal", sa.String(length=240), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidates", "current_employer_internal")
    op.drop_column("candidates", "rollen")
