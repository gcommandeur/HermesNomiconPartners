"""add referred_by to candidates

Revision ID: e1a4c7f9b2d3
Revises: b7d1e4f9a2c6
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1a4c7f9b2d3"
down_revision: str | None = "b7d1e4f9a2c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("referred_by", sa.String(240), nullable=True))


def downgrade() -> None:
    op.drop_column("candidates", "referred_by")
