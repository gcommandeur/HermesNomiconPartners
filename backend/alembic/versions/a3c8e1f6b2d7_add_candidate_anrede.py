"""add candidate anrede (gender) field for gender-correct profile generation

Revision ID: a3c8e1f6b2d7
Revises: f2a7b9c3d1e4
Create Date: 2026-07-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3c8e1f6b2d7"
down_revision: str | None = "f2a7b9c3d1e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column(
            "anrede",
            sa.Enum("FRAU", "HERR", "DIVERS", name="anrede", native_enum=False, length=16),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("candidates", "anrede")
