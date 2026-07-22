"""add expires_at to api_keys

Revision ID: 6890e93b513e
Revises: 7d65958d0528
Create Date: 2026-07-22 21:16:12.355749
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "6890e93b513e"
down_revision: str | None = "7d65958d0528"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("api_keys", "expires_at")
