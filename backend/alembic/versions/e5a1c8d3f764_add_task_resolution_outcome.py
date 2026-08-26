"""add tasks.resolution_outcome

Revision ID: e5a1c8d3f764
Revises: d2f7a3c9e651
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5a1c8d3f764"
down_revision: str | None = "d2f7a3c9e651"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("resolution_outcome", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "resolution_outcome")
