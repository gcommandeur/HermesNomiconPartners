"""add latitude/longitude to postal_localities

Revision ID: ccaba8153441
Revises: 7474f6037383
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ccaba8153441"
down_revision: str | None = "7474f6037383"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("postal_localities", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("postal_localities", sa.Column("longitude", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("postal_localities", "longitude")
    op.drop_column("postal_localities", "latitude")
