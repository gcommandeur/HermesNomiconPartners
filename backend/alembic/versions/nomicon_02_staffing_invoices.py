"""NOMICON: Rechnungen der Arbeitnehmerueberlassung (staffing_invoices, staffing_invoice_lines)

Revision ID: nomicon02invoices
Revises: nomicon01staff
Create Date: 2026-10-11

Nur in der Nomicon-Kopie (siehe KOPIE.md zu Alembic-Heads).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "nomicon02invoices"
down_revision: str | None = "nomicon01staff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        "staffing_invoices",
        sa.Column("client_company_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("amount_net", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("vat_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("amount_gross", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "invoice_status",
            sa.Enum(
                "DRAFT",
                "ISSUED",
                "DUE",
                "PAID",
                "CANCELLED",
                name="invoicestatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("payment_due_date", sa.Date(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            ["client_company_id"],
            ["client_companies.id"],
            name=op.f("fk_staffing_invoices_client_company_id_client_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_staffing_invoices_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staffing_invoices")),
    )
    op.create_index(
        op.f("ix_staffing_invoices_client_company_id"),
        "staffing_invoices",
        ["client_company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staffing_invoices_created_by_user_id"),
        "staffing_invoices",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staffing_invoices_invoice_status"),
        "staffing_invoices",
        ["invoice_status"],
        unique=False,
    )
    op.create_table(
        "staffing_invoice_lines",
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("timesheet_id", sa.Uuid(), nullable=True),
        sa.Column("assignment_id", sa.Uuid(), nullable=True),
        sa.Column("worker_name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.String(length=400), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("hours", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("rate", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("amount_net", sa.Numeric(precision=12, scale=2), nullable=False),
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
            name=op.f("fk_staffing_invoice_lines_assignment_id_staffing_assignments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["staffing_invoices.id"],
            name=op.f("fk_staffing_invoice_lines_invoice_id_staffing_invoices"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["timesheet_id"],
            ["staffing_timesheets.id"],
            name=op.f("fk_staffing_invoice_lines_timesheet_id_staffing_timesheets"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staffing_invoice_lines")),
        sa.UniqueConstraint("timesheet_id", name=op.f("uq_staffing_invoice_lines_timesheet_id")),
    )
    op.create_index(
        op.f("ix_staffing_invoice_lines_assignment_id"),
        "staffing_invoice_lines",
        ["assignment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staffing_invoice_lines_invoice_id"),
        "staffing_invoice_lines",
        ["invoice_id"],
        unique=False,
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_index(op.f("ix_staffing_invoice_lines_invoice_id"), table_name="staffing_invoice_lines")
    op.drop_index(
        op.f("ix_staffing_invoice_lines_assignment_id"), table_name="staffing_invoice_lines"
    )
    op.drop_table("staffing_invoice_lines")
    op.drop_index(op.f("ix_staffing_invoices_invoice_status"), table_name="staffing_invoices")
    op.drop_index(op.f("ix_staffing_invoices_created_by_user_id"), table_name="staffing_invoices")
    op.drop_index(op.f("ix_staffing_invoices_client_company_id"), table_name="staffing_invoices")
    op.drop_table("staffing_invoices")
