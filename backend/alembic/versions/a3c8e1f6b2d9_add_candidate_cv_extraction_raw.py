"""add candidate cv_extraction_raw column

Revision ID: a3c8e1f6b2d9
Revises: b4f7e1a9c3d6
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3c8e1f6b2d9"
down_revision: str | None = "b4f7e1a9c3d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable ohne Default (anders als fachliche_schwerpunkte/no_gos/
    # berufliche_stationen oben): "noch nie ausgelesen" ist ein legitimer,
    # haeufiger Zustand (kein CV hochgeladen), keine leere Datenstruktur.
    op.add_column("candidates", sa.Column("cv_extraction_raw", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidates", "cv_extraction_raw")
