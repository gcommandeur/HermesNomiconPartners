"""Vorstellungs-Archiv (presentation_records, unveraenderlich) und Entfernen-Antraege

Revision ID: g3b5d7f9a1c2
Revises: f2a4c6e8b0d1
Create Date: 2026-10-05

Neue Tabellen:
- presentation_records: Nachweis, was bei einer Vorstellung an eine Kanzlei gegangen ist
  (Mailtext, Empfaenger, Dateien mit Pruefsumme). Nur Admins sehen sie. Unter Postgres lehnt
  ein Trigger UPDATE und DELETE ab - Ausnahmen: (a) `retention_until` (+ retention_set_by /
  retention_set_at) darf gesetzt werden, (b) DELETE nur mit `SET LOCAL
  cc_crm.presentation_removal = 'on'` (freigegebene Entfernen-Aktion nach Ablauf der
  Aufbewahrung, siehe services/presentation_archive.py). Bewusst ohne Fremdschluessel.
- presentation_removal_requests: Antraege auf Entfernen (zweiter Admin entscheidet).
- mailing_groups.context_candidate_id: der vorgestellte Kandidat einer CV-Out-Kampagne.

Grenzen wie beim Audit-Log: der Trigger schuetzt gegen die laufende Software, nicht gegen
jemanden mit Eigentuemer-Zugang zur Datenbank. Unter SQLite gibt es keinen Trigger.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "g3b5d7f9a1c2"
down_revision: str | None = "f2a4c6e8b0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION = """
CREATE OR REPLACE FUNCTION presentation_records_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF current_setting('cc_crm.presentation_removal', true) = 'on' THEN
            RETURN OLD;
        END IF;
        RAISE EXCEPTION 'presentation_records ist unveraenderlich: DELETE ist nicht erlaubt';
    END IF;
    IF (to_jsonb(NEW) - 'retention_until' - 'retention_set_by' - 'retention_set_at')
       = (to_jsonb(OLD) - 'retention_until' - 'retention_set_by' - 'retention_set_at') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'presentation_records ist unveraenderlich: UPDATE ist nicht erlaubt';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "presentation_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("submission_id", sa.Uuid(), nullable=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=True),
        sa.Column("client_id", sa.Uuid(), nullable=True),
        sa.Column("candidate_number", sa.String(40), nullable=True),
        sa.Column("client_name", sa.String(240), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("sent_by_email", sa.String(320), nullable=True),
        sa.Column("recipient_emails", sa.JSON(), nullable=False),
        sa.Column("mail_subject", sa.String(998), nullable=False),
        sa.Column("mail_body_text", sa.Text(), nullable=False),
        sa.Column("mail_message_id", sa.String(998), nullable=True),
        sa.Column("mail_record_id", sa.Uuid(), nullable=True),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("profile_text_snapshot", sa.Text(), nullable=True),
        sa.Column("retention_until", sa.Date(), nullable=True),
        sa.Column("retention_set_by", sa.String(320), nullable=True),
        sa.Column("retention_set_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_presentation_records")),
    )
    for column in ("submission_id", "candidate_id", "client_id", "sent_at"):
        op.create_index(
            op.f(f"ix_presentation_records_{column}"), "presentation_records", [column]
        )
    op.create_table(
        "presentation_removal_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("requested_by", sa.String(320), nullable=False),
        sa.Column("decided_by", sa.String(320), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_presentation_removal_requests")),
    )
    op.create_index(
        op.f("ix_presentation_removal_requests_record_id"),
        "presentation_removal_requests",
        ["record_id"],
    )
    op.create_index(
        op.f("ix_presentation_removal_requests_status"),
        "presentation_removal_requests",
        ["status"],
    )
    with op.batch_alter_table("mailing_groups") as batch:
        batch.add_column(sa.Column("context_candidate_id", sa.Uuid(), nullable=True))

    if op.get_bind().dialect.name == "postgresql":
        op.execute(_FUNCTION)
        op.execute(
            "CREATE TRIGGER presentation_records_guard BEFORE UPDATE OR DELETE "
            "ON presentation_records FOR EACH ROW EXECUTE FUNCTION presentation_records_guard()"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS presentation_records_guard ON presentation_records")
        op.execute("DROP FUNCTION IF EXISTS presentation_records_guard()")
    with op.batch_alter_table("mailing_groups") as batch:
        batch.drop_column("context_candidate_id")
    op.drop_index(
        op.f("ix_presentation_removal_requests_status"), "presentation_removal_requests"
    )
    op.drop_index(
        op.f("ix_presentation_removal_requests_record_id"), "presentation_removal_requests"
    )
    op.drop_table("presentation_removal_requests")
    for column in ("sent_at", "client_id", "candidate_id", "submission_id"):
        op.drop_index(op.f(f"ix_presentation_records_{column}"), "presentation_records")
    op.drop_table("presentation_records")
