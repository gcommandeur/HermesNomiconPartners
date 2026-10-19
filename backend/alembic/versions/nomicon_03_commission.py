"""NOMICON: Provisionsmodell (commission_user_ranks)

Revision ID: nomicon03commission
Revises: nomicon02invoices
Create Date: 2026-10-11

Nur in der Nomicon-Kopie (siehe KOPIE.md zu Alembic-Heads).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "nomicon03commission"
down_revision: str | None = "nomicon02invoices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        "commission_user_ranks",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("rank_key", sa.String(length=40), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("updated_by", sa.String(length=320), nullable=True),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_commission_user_ranks_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_commission_user_ranks")),
        sa.UniqueConstraint("user_id", name=op.f("uq_commission_user_ranks_user_id")),
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_table("commission_user_ranks")
