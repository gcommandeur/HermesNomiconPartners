"""add operational crm fields

Revision ID: 5c1c4f821b90
Revises: 411de3299065
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5c1c4f821b90"
down_revision: str | None = "411de3299065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for _name, column in [
        ("candidate_number", sa.Column("candidate_number", sa.String(40))),
        ("qualification", sa.Column("qualification", sa.String(240))),
        ("available_from", sa.Column("available_from", sa.Date())),
        ("last_contact_at", sa.Column("last_contact_at", sa.Date())),
        ("next_step", sa.Column("next_step", sa.String(240))),
        (
            "cv_available",
            sa.Column("cv_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        ),
        ("short_profile", sa.Column("short_profile", sa.Text())),
        (
            "consent_received",
            sa.Column("consent_received", sa.Boolean(), nullable=False, server_default=sa.false()),
        ),
    ]:
        op.add_column("candidates", column)
    op.create_index(
        "ix_candidates_candidate_number", "candidates", ["candidate_number"], unique=True
    )

    client_columns = [
        sa.Column("region", sa.String(160)),
        sa.Column("company_size", sa.String(120)),
        sa.Column("focus", sa.String(240)),
        sa.Column("linkedin_url", sa.String(500)),
        sa.Column("last_contact_at", sa.Date()),
        sa.Column("next_follow_up_at", sa.Date()),
        sa.Column("terms_status", sa.String(40), nullable=False, server_default="not_sent"),
        sa.Column("fee_percentage", sa.Numeric(5, 2), nullable=False, server_default="27.00"),
        sa.Column(
            "refund_terms",
            sa.Text(),
            nullable=False,
            server_default="50 % vor Antritt; 50 % im ersten Monat; 25 % im zweiten Monat",
        ),
        sa.Column("guarantee_period_months", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("special_terms", sa.Text()),
        sa.Column("commercial_notes", sa.Text()),
    ]
    for column in client_columns:
        op.add_column("client_companies", column)

    submission_columns = [
        sa.Column("sent_profile_text", sa.Text()),
        sa.Column("salary_at_submission", sa.String(120)),
        sa.Column("fee_percentage", sa.Numeric(5, 2)),
        sa.Column("expected_fee", sa.Numeric(12, 2)),
        sa.Column("refund_terms", sa.Text()),
        sa.Column("feedback_summary", sa.Text()),
        sa.Column("next_step", sa.String(240)),
        sa.Column("follow_up_at", sa.DateTime(timezone=True)),
        sa.Column("owner", sa.String(160)),
        sa.Column("outlook_draft_created", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("email_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
    ]
    for column in submission_columns:
        op.add_column("candidate_submissions", column)
    op.create_index(
        "ix_candidate_submissions_follow_up_at", "candidate_submissions", ["follow_up_at"]
    )

    for column in [
        sa.Column("search_radius_km", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("work_model", sa.String(120)),
        sa.Column("qualifications", sa.Text()),
        sa.Column("experience", sa.Text()),
    ]:
        op.add_column("job_mandates", column)

    op.create_table(
        "documents",
        sa.Column("owner_type", sa.String(40), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(60), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(120)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("uploaded_by", sa.String(160)),
        sa.Column("sent_with_submission_id", sa.Uuid()),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["sent_with_submission_id"], ["candidate_submissions.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_documents_owner", "documents", ["owner_type", "owner_id"])
    op.create_index(
        "ix_documents_sent_with_submission_id", "documents", ["sent_with_submission_id"]
    )

    op.create_table(
        "sourcing_metrics",
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("campaign", sa.String(240)),
        sa.Column("pitches", sa.Integer(), nullable=False),
        sa.Column("responses", sa.Integer(), nullable=False),
        sa.Column("positive_responses", sa.Integer(), nullable=False),
        sa.Column("qualification_calls", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_sourcing_metrics_period_start", "sourcing_metrics", ["period_start"])
    op.create_index("ix_sourcing_metrics_period_end", "sourcing_metrics", ["period_end"])

    op.create_table(
        "email_draft_logs",
        sa.Column("template_key", sa.String(80), nullable=False),
        sa.Column("candidate_id", sa.Uuid()),
        sa.Column("client_company_id", sa.Uuid()),
        sa.Column("candidate_submission_id", sa.Uuid()),
        sa.Column("recipient", sa.String(320)),
        sa.Column("subject", sa.String(240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("external_draft_id", sa.String(240)),
        sa.Column("drafted_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["client_company_id"], ["client_companies.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_submission_id"], ["candidate_submissions.id"], ondelete="SET NULL"
        ),
    )
    for column in ["template_key", "candidate_id", "client_company_id", "candidate_submission_id"]:
        op.create_index(f"ix_email_draft_logs_{column}", "email_draft_logs", [column])


def downgrade() -> None:
    op.drop_table("email_draft_logs")
    op.drop_table("sourcing_metrics")
    op.drop_table("documents")
    for name in ["experience", "qualifications", "work_model", "search_radius_km"]:
        op.drop_column("job_mandates", name)
    op.drop_index("ix_candidate_submissions_follow_up_at", table_name="candidate_submissions")
    for name in [
        "email_sent",
        "outlook_draft_created",
        "owner",
        "follow_up_at",
        "next_step",
        "feedback_summary",
        "refund_terms",
        "expected_fee",
        "fee_percentage",
        "salary_at_submission",
        "sent_profile_text",
    ]:
        op.drop_column("candidate_submissions", name)
    for name in [
        "commercial_notes",
        "special_terms",
        "payment_terms_days",
        "guarantee_period_months",
        "refund_terms",
        "fee_percentage",
        "terms_status",
        "next_follow_up_at",
        "last_contact_at",
        "linkedin_url",
        "focus",
        "company_size",
        "region",
    ]:
        op.drop_column("client_companies", name)
    op.drop_index("ix_candidates_candidate_number", table_name="candidates")
    for name in [
        "consent_received",
        "short_profile",
        "cv_available",
        "next_step",
        "last_contact_at",
        "available_from",
        "qualification",
        "candidate_number",
    ]:
        op.drop_column("candidates", name)
