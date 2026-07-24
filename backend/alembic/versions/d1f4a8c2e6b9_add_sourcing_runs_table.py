"""add sourcing_runs table (Stop-Mechanismus fuer den Hintergrund-Sourcing-Lauf)

Revision ID: d1f4a8c2e6b9
Revises: c4d7e1a9f3b2
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d1f4a8c2e6b9"
down_revision: str | None = "c4d7e1a9f3b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sourcing_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum(
                "STEUERBERATERVERZEICHNIS",
                "WPK_BERUFSREGISTER",
                "BRAK_ANWALTSVERZEICHNIS",
                "KANZLEI_TEAM_PAGE",
                name="sourcingsourcetype",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "RUNNING",
                "COMPLETED",
                "STOPPED",
                name="sourcingrunstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("processed", sa.Integer(), nullable=False),
        sa.Column("leads_created", sa.Integer(), nullable=False),
        sa.Column("stop_requested", sa.Boolean(), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sourcing_runs")),
    )
    op.create_index(op.f("ix_sourcing_runs_status"), "sourcing_runs", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_sourcing_runs_status"), table_name="sourcing_runs")
    op.drop_table("sourcing_runs")
