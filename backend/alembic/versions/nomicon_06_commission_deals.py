"""NOMICON: Verlaengerungen von Einsaetzen (Deals im Provisionsmodell), Rang Junior entfaellt

Revision ID: nomicon06deals
Revises: nomicon05engagement
Create Date: 2026-10-16

Nur in der Nomicon-Kopie (siehe KOPIE.md). Der Rang `junior` gibt es im neuen Karriereplan nicht
mehr; bestehende Zuordnungen wandern auf `consultant` (die Rueckrichtung stellt sie nicht her).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "nomicon06deals"
down_revision: str | None = "nomicon05engagement"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        "staffing_assignment_extensions",
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("previous_end", sa.Date(), nullable=False),
        sa.Column("new_end", sa.Date(), nullable=False),
        sa.Column("extended_on", sa.Date(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
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
            ["assignment_id"],
            ["staffing_assignments.id"],
            name=op.f("fk_staffing_assignment_extensions_assignment_id_staffing_assignments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_staffing_assignment_extensions_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staffing_assignment_extensions")),
    )
    op.create_index(
        op.f("ix_staffing_assignment_extensions_assignment_id"),
        "staffing_assignment_extensions",
        ["assignment_id"],
        unique=False,
    )
    op.execute(
        "UPDATE commission_user_ranks SET rank_key = 'consultant' WHERE rank_key = 'junior'"
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_index(
        op.f("ix_staffing_assignment_extensions_assignment_id"),
        table_name="staffing_assignment_extensions",
    )
    op.drop_table("staffing_assignment_extensions")
