"""NOMICON: Arbeitnehmerueberlassung (staffing_*-Tabellen)

Revision ID: nomicon01staff
Revises: g3b5d7f9a1c2
Create Date: 2026-10-11

Nur in der Nomicon-Kopie. Entsteht zwischen Hermes-Migrationen spaeter ein zweiter Head,
muss eine Merge-Migration her (siehe KOPIE.md).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "nomicon01staff"
down_revision: str | None = "g3b5d7f9a1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this migration."""
    op.create_table(
        "staffing_workers",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "APPLICANT",
                "ACTIVE",
                "DORMANT",
                "LEFT",
                name="staffingworkerstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("entry_date", sa.Date(), nullable=True),
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("hourly_wage", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("pay_grade", sa.String(length=80), nullable=True),
        sa.Column("weekly_hours", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("work_permit_valid_until", sa.Date(), nullable=True),
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
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_staffing_workers_candidate_id_candidates"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staffing_workers")),
        sa.UniqueConstraint("candidate_id", name=op.f("uq_staffing_workers_candidate_id")),
    )
    op.create_index(
        op.f("ix_staffing_workers_status"), "staffing_workers", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_staffing_workers_work_permit_valid_until"),
        "staffing_workers",
        ["work_permit_valid_until"],
        unique=False,
    )
    op.create_table(
        "staffing_contracts",
        sa.Column("client_company_id", sa.Uuid(), nullable=False),
        sa.Column("contract_number", sa.String(length=80), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("industry_sector", sa.String(length=120), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "ACTIVE",
                "EXPIRED",
                "TERMINATED",
                name="staffingcontractstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
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
            name=op.f("fk_staffing_contracts_client_company_id_client_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_staffing_contracts_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staffing_contracts")),
    )
    op.create_index(
        op.f("ix_staffing_contracts_client_company_id"),
        "staffing_contracts",
        ["client_company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staffing_contracts_status"), "staffing_contracts", ["status"], unique=False
    )
    op.create_table(
        "staffing_licenses",
        sa.Column("authority", sa.String(length=160), nullable=False),
        sa.Column("file_number", sa.String(length=80), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("reminder_days", sa.Integer(), nullable=False),
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
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_staffing_licenses_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staffing_licenses")),
    )
    op.create_index(
        op.f("ix_staffing_licenses_valid_to"), "staffing_licenses", ["valid_to"], unique=False
    )
    op.create_table(
        "staffing_assignments",
        sa.Column("worker_id", sa.Uuid(), nullable=False),
        sa.Column("client_company_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("planned_end_date", sa.Date(), nullable=True),
        sa.Column("actual_end_date", sa.Date(), nullable=True),
        sa.Column("location", sa.String(length=240), nullable=True),
        sa.Column("activity", sa.String(length=240), nullable=True),
        sa.Column("billing_rate", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("hourly_wage", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PLANNED",
                "ACTIVE",
                "ENDED",
                "ABORTED",
                name="staffingassignmentstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
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
            name=op.f("fk_staffing_assignments_client_company_id_client_companies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["staffing_contracts.id"],
            name=op.f("fk_staffing_assignments_contract_id_staffing_contracts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_staffing_assignments_owner_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["staffing_workers.id"],
            name=op.f("fk_staffing_assignments_worker_id_staffing_workers"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staffing_assignments")),
    )
    op.create_index(
        op.f("ix_staffing_assignments_client_company_id"),
        "staffing_assignments",
        ["client_company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staffing_assignments_contract_id"),
        "staffing_assignments",
        ["contract_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staffing_assignments_owner_user_id"),
        "staffing_assignments",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staffing_assignments_start_date"),
        "staffing_assignments",
        ["start_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staffing_assignments_status"), "staffing_assignments", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_staffing_assignments_worker_id"),
        "staffing_assignments",
        ["worker_id"],
        unique=False,
    )
    op.create_table(
        "staffing_assignment_checklist_items",
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column(
            "item_key",
            sa.Enum(
                "EMPLOYMENT_CONTRACT",
                "INFO_LEAFLET",
                "SUPPLY_CONTRACT",
                "SPECIFICATION",
                "SAFETY_BRIEFING",
                "PPE_PROTOCOL",
                name="staffingchecklistkey",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("done", sa.Boolean(), nullable=False),
        sa.Column("done_on", sa.Date(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
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
            name=op.f("fk_staffing_assignment_checklist_items_assignment_id_staffing_assignments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_staffing_assignment_checklist_items_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staffing_assignment_checklist_items")),
        sa.UniqueConstraint(
            "assignment_id",
            "item_key",
            name=op.f("uq_staffing_assignment_checklist_items_assignment_id"),
        ),
    )
    op.create_index(
        op.f("ix_staffing_assignment_checklist_items_assignment_id"),
        "staffing_assignment_checklist_items",
        ["assignment_id"],
        unique=False,
    )
    op.create_table(
        "staffing_timesheets",
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN",
                "SUBMITTED",
                "APPROVED",
                "REJECTED",
                name="staffingtimesheetstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_name", sa.String(length=160), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("approval_token_hash", sa.String(length=64), nullable=True),
        sa.Column("approval_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_token_used_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_staffing_timesheets_assignment_id_staffing_assignments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staffing_timesheets")),
        sa.UniqueConstraint(
            "approval_token_hash", name=op.f("uq_staffing_timesheets_approval_token_hash")
        ),
        sa.UniqueConstraint(
            "assignment_id", "period_start", name=op.f("uq_staffing_timesheets_assignment_id")
        ),
    )
    op.create_index(
        op.f("ix_staffing_timesheets_assignment_id"),
        "staffing_timesheets",
        ["assignment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_staffing_timesheets_status"), "staffing_timesheets", ["status"], unique=False
    )
    op.create_table(
        "staffing_timesheet_entries",
        sa.Column("timesheet_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column("break_minutes", sa.Integer(), nullable=False),
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
            ["timesheet_id"],
            ["staffing_timesheets.id"],
            name=op.f("fk_staffing_timesheet_entries_timesheet_id_staffing_timesheets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staffing_timesheet_entries")),
        sa.UniqueConstraint(
            "timesheet_id", "work_date", name=op.f("uq_staffing_timesheet_entries_timesheet_id")
        ),
    )
    op.create_index(
        op.f("ix_staffing_timesheet_entries_timesheet_id"),
        "staffing_timesheet_entries",
        ["timesheet_id"],
        unique=False,
    )


def downgrade() -> None:
    """Revert this migration."""
    op.drop_index(
        op.f("ix_staffing_timesheet_entries_timesheet_id"), table_name="staffing_timesheet_entries"
    )
    op.drop_table("staffing_timesheet_entries")
    op.drop_index(op.f("ix_staffing_timesheets_status"), table_name="staffing_timesheets")
    op.drop_index(op.f("ix_staffing_timesheets_assignment_id"), table_name="staffing_timesheets")
    op.drop_table("staffing_timesheets")
    op.drop_index(
        op.f("ix_staffing_assignment_checklist_items_assignment_id"),
        table_name="staffing_assignment_checklist_items",
    )
    op.drop_table("staffing_assignment_checklist_items")
    op.drop_index(op.f("ix_staffing_assignments_worker_id"), table_name="staffing_assignments")
    op.drop_index(op.f("ix_staffing_assignments_status"), table_name="staffing_assignments")
    op.drop_index(op.f("ix_staffing_assignments_start_date"), table_name="staffing_assignments")
    op.drop_index(op.f("ix_staffing_assignments_owner_user_id"), table_name="staffing_assignments")
    op.drop_index(op.f("ix_staffing_assignments_contract_id"), table_name="staffing_assignments")
    op.drop_index(
        op.f("ix_staffing_assignments_client_company_id"), table_name="staffing_assignments"
    )
    op.drop_table("staffing_assignments")
    op.drop_index(op.f("ix_staffing_licenses_valid_to"), table_name="staffing_licenses")
    op.drop_table("staffing_licenses")
    op.drop_index(op.f("ix_staffing_contracts_status"), table_name="staffing_contracts")
    op.drop_index(op.f("ix_staffing_contracts_client_company_id"), table_name="staffing_contracts")
    op.drop_table("staffing_contracts")
    op.drop_index(
        op.f("ix_staffing_workers_work_permit_valid_until"), table_name="staffing_workers"
    )
    op.drop_index(op.f("ix_staffing_workers_status"), table_name="staffing_workers")
    op.drop_table("staffing_workers")
