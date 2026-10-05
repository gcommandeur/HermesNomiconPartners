"""candidates: Einwilligungsnachweis (consent_recorded_at, consent_source) und anonymized_at

Revision ID: f2a4c6e8b0d1
Revises: e1c3d5a7b9f2
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2a4c6e8b0d1"
down_revision: str | None = "e1c3d5a7b9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("candidates") as batch:
        batch.add_column(
            sa.Column("consent_recorded_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("consent_source", sa.String(60), nullable=True))
        batch.add_column(sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("candidates") as batch:
        batch.drop_column("anonymized_at")
        batch.drop_column("consent_source")
        batch.drop_column("consent_recorded_at")
