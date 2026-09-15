"""M365-Postfach-Integration: provider/OAuth-Felder auf mail_accounts,
Graph-Kalender-Mapping auf calendar_events

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-15

Auftrag "M365-Postfach-Integration": MailAccount bekommt einen zweiten
Provider (microsoft_graph, OAuth-Login statt IMAP/SMTP-Passwort) neben dem
bestehenden imap_smtp - siehe models/mail.py::MailAccount-Docstring. Die
bisher NOT NULL gesetzten IMAP/SMTP-Felder werden auf nullable gelockert
(nur fuer microsoft_graph-Zeilen leer, bestehende imap_smtp-Zeilen bleiben
unveraendert befuellt), neue oauth_*-Spalten kommen dazu.

CalendarEvent bekommt ein Mapping zum Microsoft-Graph-Kalender-Event
(bidirektionaler Kalender-Sync, Teil derselben Integration).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("mail_accounts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "provider",
                sa.String(length=16),
                nullable=False,
                server_default="imap_smtp",
            )
        )
        batch_op.add_column(sa.Column("encrypted_oauth_refresh_token", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("oauth_scopes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("oauth_status", sa.String(length=20), nullable=True))
        batch_op.add_column(
            sa.Column("oauth_connected_by_user_id", sa.Uuid(), nullable=True)
        )
        batch_op.add_column(sa.Column("graph_delta_link", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("graph_calendar_delta_link", sa.Text(), nullable=True))
        batch_op.alter_column("imap_host", existing_type=sa.String(length=255), nullable=True)
        batch_op.alter_column("smtp_host", existing_type=sa.String(length=255), nullable=True)
        batch_op.alter_column("username", existing_type=sa.String(length=320), nullable=True)
        batch_op.alter_column("encrypted_password", existing_type=sa.Text(), nullable=True)
        batch_op.create_index(
            op.f("ix_mail_accounts_provider"), ["provider"], unique=False
        )
        batch_op.create_foreign_key(
            op.f("fk_mail_accounts_oauth_connected_by_user_id_users"),
            "users",
            ["oauth_connected_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("calendar_events") as batch_op:
        batch_op.add_column(sa.Column("external_graph_event_id", sa.String(length=200), nullable=True))
        batch_op.add_column(
            sa.Column("external_graph_last_synced_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index(
            op.f("ix_calendar_events_external_graph_event_id"),
            ["external_graph_event_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("calendar_events") as batch_op:
        batch_op.drop_index(op.f("ix_calendar_events_external_graph_event_id"))
        batch_op.drop_column("external_graph_last_synced_at")
        batch_op.drop_column("external_graph_event_id")

    with op.batch_alter_table("mail_accounts") as batch_op:
        batch_op.drop_constraint(
            op.f("fk_mail_accounts_oauth_connected_by_user_id_users"), type_="foreignkey"
        )
        batch_op.drop_index(op.f("ix_mail_accounts_provider"))
        batch_op.alter_column("encrypted_password", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("username", existing_type=sa.String(length=320), nullable=False)
        batch_op.alter_column("smtp_host", existing_type=sa.String(length=255), nullable=False)
        batch_op.alter_column("imap_host", existing_type=sa.String(length=255), nullable=False)
        batch_op.drop_column("graph_calendar_delta_link")
        batch_op.drop_column("graph_delta_link")
        batch_op.drop_column("oauth_connected_by_user_id")
        batch_op.drop_column("oauth_status")
        batch_op.drop_column("oauth_scopes")
        batch_op.drop_column("encrypted_oauth_refresh_token")
        batch_op.drop_column("provider")
