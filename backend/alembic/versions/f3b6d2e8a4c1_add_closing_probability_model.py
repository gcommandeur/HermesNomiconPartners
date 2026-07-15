"""add closing probability model (submission scoring fields + region_modifiers table)

Revision ID: f3b6d2e8a4c1
Revises: e1a4c7f9b2d3
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f3b6d2e8a4c1"
down_revision: str | None = "e1a4c7f9b2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("candidate_submissions", sa.Column("pain_staerke", sa.Integer(), nullable=True))
    op.add_column(
        "candidate_submissions", sa.Column("entscheidungsklarheit", sa.Integer(), nullable=True)
    )
    op.add_column("candidate_submissions", sa.Column("markt_fit", sa.Integer(), nullable=True))
    op.add_column("candidate_submissions", sa.Column("momentum", sa.Integer(), nullable=True))
    op.add_column(
        "candidate_submissions", sa.Column("closing_probability", sa.Float(), nullable=True)
    )
    op.add_column(
        "candidate_submissions",
        sa.Column("closing_status", sa.String(length=16), nullable=True),
    )

    op.create_table(
        "region_modifiers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("plz_prefix", sa.String(length=10), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=True),
        sa.Column("modifier", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_region_modifiers_plz_prefix", "region_modifiers", ["plz_prefix"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_region_modifiers_plz_prefix", table_name="region_modifiers")
    op.drop_table("region_modifiers")
    op.drop_column("candidate_submissions", "closing_status")
    op.drop_column("candidate_submissions", "closing_probability")
    op.drop_column("candidate_submissions", "momentum")
    op.drop_column("candidate_submissions", "markt_fit")
    op.drop_column("candidate_submissions", "entscheidungsklarheit")
    op.drop_column("candidate_submissions", "pain_staerke")
