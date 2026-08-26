"""add candidate_submissions.archived_at

Revision ID: f7c2b6e9a103
Revises: e5a1c8d3f764
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f7c2b6e9a103"
down_revision: str | None = "e5a1c8d3f764"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "candidate_submissions", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("candidate_submissions", "archived_at")
