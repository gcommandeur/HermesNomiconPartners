"""api_keys.scope: service | mcp

Revision ID: a3e5c7b9d1f2
Revises: f1c3a7d9b5e2
Create Date: 2026-10-04

Schluessel fuer die lesende Claude-Schnittstelle (an einen echten Nutzer
gebunden, nur fuer /api/v1/mcp gueltig). Bestehende Schluessel bleiben "service".
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3e5c7b9d1f2"
down_revision: str | None = "f1c3a7d9b5e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("api_keys") as batch:
        batch.add_column(
            sa.Column("scope", sa.String(20), server_default="service", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("api_keys") as batch:
        batch.drop_column("scope")
