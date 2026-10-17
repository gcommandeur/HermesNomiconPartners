"""NOMICON: Vorzeiten beim Kunden (früher geleistete Überlassungszeiten)

Revision ID: nomicon07prior
Revises: nomicon06deals
Create Date: 2026-10-17

Nur in der Nomicon-Kopie. Neue Tabelle `staffing_prior_periods`; es werden keine Werte erfunden
und keine bestehenden Daten verändert.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "nomicon07prior"
down_revision: str | None = "nomicon06deals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        "staffing_prior_periods",
        sa.Column("worker_id", sa.Uuid(), nullable=False),
        sa.Column("client_company_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
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
            ["worker_id"],
            ["staffing_workers.id"],
            name=op.f("fk_staffing_prior_periods_worker_id_staffing_workers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["client_company_id"],
            ["client_companies.id"],
            name=op.f("fk_staffing_prior_periods_client_company_id_client_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_staffing_prior_periods_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staffing_prior_periods")),
    )
    op.create_index(
        op.f("ix_staffing_prior_periods_worker_id"),
        "staffing_prior_periods",
        ["worker_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staffing_prior_periods_client_company_id"),
        "staffing_prior_periods",
        ["client_company_id"],
        unique=False,
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_index(
        op.f("ix_staffing_prior_periods_client_company_id"), table_name="staffing_prior_periods"
    )
    op.drop_index(op.f("ix_staffing_prior_periods_worker_id"), table_name="staffing_prior_periods")
    op.drop_table("staffing_prior_periods")
