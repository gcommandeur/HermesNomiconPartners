"""add documents.has_generic_filename (flag for generic CV filenames)

Revision ID: a8c2f5e9d6b3
Revises: f3b6d2e8a4c1
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a8c2f5e9d6b3"
down_revision: str | None = "f3b6d2e8a4c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("has_generic_filename", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("documents", "has_generic_filename")
