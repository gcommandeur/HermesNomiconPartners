"""NOMICON: Kandidatenstatus (candidate_engagement_prefs)

Revision ID: nomicon05engagement
Revises: nomicon04views
Create Date: 2026-10-14

Nur in der Nomicon-Kopie (siehe KOPIE.md).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "nomicon05engagement"
down_revision: str | None = "nomicon04views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        "candidate_engagement_prefs",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("open_for_direct", sa.String(length=10), nullable=False),
        sa.Column("open_for_staffing", sa.String(length=10), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_candidate_engagement_prefs_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_candidate_engagement_prefs_updated_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_engagement_prefs")),
        sa.UniqueConstraint("candidate_id", name=op.f("uq_candidate_engagement_prefs_candidate_id")),
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_table("candidate_engagement_prefs")
