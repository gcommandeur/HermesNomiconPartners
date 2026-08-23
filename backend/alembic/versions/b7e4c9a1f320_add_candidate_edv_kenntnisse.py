"""add candidate edv_kenntnisse field

Revision ID: b7e4c9a1f320
Revises: d8f3a2c6e910
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7e4c9a1f320"
down_revision: str | None = "d8f3a2c6e910"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column(
            "edv_kenntnisse",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("candidates", "edv_kenntnisse")
