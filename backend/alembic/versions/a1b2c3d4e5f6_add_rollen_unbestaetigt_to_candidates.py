"""add rollen_unbestaetigt to candidates

Revision ID: a1b2c3d4e5f6
Revises: f7c2b6e9a103
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f7c2b6e9a103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column(
            "rollen_unbestaetigt", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("candidates", "rollen_unbestaetigt")
