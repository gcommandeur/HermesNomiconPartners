"""NOMICON: Bestätigung "Keine Vorzeiten" je Paar (Leiharbeitnehmer, Kunde)

Revision ID: nomicon09priorconf
Revises: nomicon08equalpay
Create Date: 2026-10-19

Nur in der Nomicon-Kopie. Neue, leere Tabelle `staffing_prior_period_confirmations`; es werden keine
Werte erfunden und keine bestehenden Daten verändert.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "nomicon09priorconf"
down_revision: str | None = "nomicon08equalpay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "staffing_prior_period_confirmations"


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        TABLE,
        sa.Column("worker_id", sa.Uuid(), nullable=False),
        sa.Column("client_company_id", sa.Uuid(), nullable=False),
        sa.Column("confirmed_on", sa.Date(), nullable=False),
        sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
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
            name=op.f("fk_staffing_prior_period_confirmations_worker_id_staffing_workers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["client_company_id"],
            ["client_companies.id"],
            name=op.f("fk_staffing_prior_period_confirmations_client_company_id_client_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"],
            ["users.id"],
            name=op.f("fk_staffing_prior_period_confirmations_confirmed_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staffing_prior_period_confirmations")),
        sa.UniqueConstraint(
            "worker_id",
            "client_company_id",
            name=op.f("uq_staffing_prior_period_confirmations_worker_id"),
        ),
    )
    op.create_index(
        op.f("ix_staffing_prior_period_confirmations_worker_id"), TABLE, ["worker_id"], unique=False
    )
    op.create_index(
        op.f("ix_staffing_prior_period_confirmations_client_company_id"),
        TABLE,
        ["client_company_id"],
        unique=False,
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_index(
        op.f("ix_staffing_prior_period_confirmations_client_company_id"), table_name=TABLE
    )
    op.drop_index(op.f("ix_staffing_prior_period_confirmations_worker_id"), table_name=TABLE)
    op.drop_table(TABLE)
