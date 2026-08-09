"""add mail_accounts + mail_messages, users.default_send_account_id

Grundlage der IMAP-Postfach-Anbindung: verbundene Postfaecher inkl.
Fernet-verschluesselter Zugangsdaten (mail_accounts) und die daraus
eingelesenen Nachrichten (mail_messages, Dedup ueber message_id).
users.default_send_account_id ist der persoenliche Override fuer das
Standard-Absenderpostfach (Vorrang vor mail_accounts.default_for_cv_out).

Revision ID: c4e8a1f7b920
Revises: b7d3f1a9c5e2
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4e8a1f7b920"
down_revision: str | None = "b7d3f1a9c5e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mail_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("address", sa.String(length=320), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("imap_host", sa.String(length=255), nullable=False),
        sa.Column("imap_port", sa.Integer(), nullable=False),
        sa.Column("imap_use_ssl", sa.Boolean(), nullable=False),
        sa.Column("smtp_host", sa.String(length=255), nullable=False),
        sa.Column("smtp_port", sa.Integer(), nullable=False),
        sa.Column("smtp_use_ssl", sa.Boolean(), nullable=False),
        sa.Column("username", sa.String(length=320), nullable=False),
        sa.Column("encrypted_password", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("default_for_cv_out", sa.Boolean(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_uid", sa.String(length=80), nullable=True),
        sa.Column("sync_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_mail_accounts"),
        sa.UniqueConstraint("address", name="uq_mail_accounts_address"),
    )
    op.create_index("ix_mail_accounts_address", "mail_accounts", ["address"])
    op.create_index("ix_mail_accounts_is_active", "mail_accounts", ["is_active"])

    op.create_table(
        "mail_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mail_account_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.String(length=998), nullable=False),
        sa.Column("imap_uid", sa.String(length=80), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("from_name", sa.String(length=320), nullable=True),
        sa.Column("from_address", sa.String(length=320), nullable=True),
        sa.Column("subject", sa.String(length=998), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_linkedin", sa.Boolean(), nullable=False),
        sa.Column("match_status", sa.String(length=24), nullable=False),
        sa.Column("matched_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("matched_contact_person_id", sa.Uuid(), nullable=True),
        sa.Column("matched_client_company_id", sa.Uuid(), nullable=True),
        sa.Column("created_activity_id", sa.Uuid(), nullable=True),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_mail_messages"),
        sa.UniqueConstraint("message_id", name="uq_mail_messages_message_id"),
        sa.ForeignKeyConstraint(
            ["mail_account_id"],
            ["mail_accounts.id"],
            name="fk_mail_messages_mail_account_id_mail_accounts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["matched_candidate_id"],
            ["candidates.id"],
            name="fk_mail_messages_matched_candidate_id_candidates",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["matched_contact_person_id"],
            ["contact_persons.id"],
            name="fk_mail_messages_matched_contact_person_id_contact_persons",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["matched_client_company_id"],
            ["client_companies.id"],
            name="fk_mail_messages_matched_client_company_id_client_companies",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_activity_id"],
            ["activities.id"],
            name="fk_mail_messages_created_activity_id_activities",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_mail_messages_mail_account_id", "mail_messages", ["mail_account_id"])
    op.create_index("ix_mail_messages_message_id", "mail_messages", ["message_id"])
    op.create_index("ix_mail_messages_direction", "mail_messages", ["direction"])
    op.create_index("ix_mail_messages_from_address", "mail_messages", ["from_address"])
    op.create_index("ix_mail_messages_received_at", "mail_messages", ["received_at"])
    op.create_index("ix_mail_messages_is_linkedin", "mail_messages", ["is_linkedin"])
    op.create_index("ix_mail_messages_match_status", "mail_messages", ["match_status"])
    op.create_index(
        "ix_mail_messages_matched_candidate_id", "mail_messages", ["matched_candidate_id"]
    )
    op.create_index(
        "ix_mail_messages_matched_contact_person_id",
        "mail_messages",
        ["matched_contact_person_id"],
    )
    op.create_index(
        "ix_mail_messages_matched_client_company_id",
        "mail_messages",
        ["matched_client_company_id"],
    )

    # SQLite kann eine Fremdschluessel-Constraint nicht per plain ALTER TABLE
    # nachtraeglich hinzufuegen - batch_alter_table umgeht das (auf Postgres
    # ein direktes ALTER TABLE, gleiches Muster wie ec9beff2cbaa).
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("default_send_account_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_users_default_send_account_id_mail_accounts",
            "mail_accounts",
            ["default_send_account_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("fk_users_default_send_account_id_mail_accounts", type_="foreignkey")
        batch_op.drop_column("default_send_account_id")

    op.drop_table("mail_messages")
    op.drop_table("mail_accounts")
