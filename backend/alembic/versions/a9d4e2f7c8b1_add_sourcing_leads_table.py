"""add sourcing_leads table (Sourcing-Agent Review-Ebene vor Kandidaten-Uebernahme)

Revision ID: a9d4e2f7c8b1
Revises: 6890e93b513e
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9d4e2f7c8b1"
down_revision: str | None = "6890e93b513e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sourcing_leads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
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
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("current_employer", sa.String(length=240), nullable=True),
        sa.Column("city", sa.String(length=160), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("matched_client_company_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "APPROVED",
                "REJECTED",
                "POSSIBLE_DUPLICATE",
                name="sourcingleadstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("duplicate_of_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("created_candidate_id", sa.Uuid(), nullable=True),
        sa.Column(
            "found_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["matched_client_company_id"],
            ["client_companies.id"],
            name=op.f("fk_sourcing_leads_matched_client_company_id_client_companies"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_candidate_id"],
            ["candidates.id"],
            name=op.f("fk_sourcing_leads_duplicate_of_candidate_id_candidates"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_candidate_id"],
            ["candidates.id"],
            name=op.f("fk_sourcing_leads_created_candidate_id_candidates"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            name=op.f("fk_sourcing_leads_reviewed_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sourcing_leads")),
    )
    op.create_index(op.f("ix_sourcing_leads_source_type"), "sourcing_leads", ["source_type"])
    op.create_index(op.f("ix_sourcing_leads_last_name"), "sourcing_leads", ["last_name"])
    op.create_index(op.f("ix_sourcing_leads_postal_code"), "sourcing_leads", ["postal_code"])
    op.create_index(op.f("ix_sourcing_leads_status"), "sourcing_leads", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_sourcing_leads_status"), table_name="sourcing_leads")
    op.drop_index(op.f("ix_sourcing_leads_postal_code"), table_name="sourcing_leads")
    op.drop_index(op.f("ix_sourcing_leads_last_name"), table_name="sourcing_leads")
    op.drop_index(op.f("ix_sourcing_leads_source_type"), table_name="sourcing_leads")
    op.drop_table("sourcing_leads")
