"""audit_logs append-only (Trigger, nur Postgres)

Revision ID: f4b7d1a8c2e5
Revises: e3a6c9d2f5b8
Create Date: 2026-10-03

Der Audit-Log darf von der laufenden Anwendung nicht veraendert oder geloescht
werden. Ein Trigger lehnt UPDATE und DELETE ab - mit genau EINER Ausnahme: die
DSGVO-Anonymisierung (CandidateService.anonymize) setzt in ihrer Transaktion
`SET LOCAL cc_crm.audit_redaction = 'on'` und darf dann ausschliesslich
`old_values`/`new_values` ueberschreiben (Schwaerzung); alle anderen Spalten
muessen gleich bleiben, geloescht wird nie.

Grenzen (bewusst, siehe docs/PLAN_SKALIERUNG.md 2a): schuetzt gegen die laufende
Software, nicht gegen jemanden mit Eigentuemer-Zugang zur Datenbank (der kann den
Trigger entfernen). TRUNCATE ist nicht gesperrt (die Tests brauchen es). Unter
SQLite (lokale Entwicklung/Tests) gibt es keinen Trigger.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f4b7d1a8c2e5"
down_revision: str | None = "e3a6c9d2f5b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_logs_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'audit_logs ist append-only: DELETE ist nicht erlaubt';
    END IF;
    IF current_setting('cc_crm.audit_redaction', true) = 'on'
       AND NEW.id = OLD.id
       AND NEW.entity_type = OLD.entity_type
       AND NEW.entity_id = OLD.entity_id
       AND NEW.action = OLD.action
       AND NEW.changed_at IS NOT DISTINCT FROM OLD.changed_at
       AND NEW.changed_by IS NOT DISTINCT FROM OLD.changed_by THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'audit_logs ist append-only: UPDATE ist nicht erlaubt';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(_FUNCTION)
    op.execute(
        "CREATE TRIGGER audit_logs_guard BEFORE UPDATE OR DELETE ON audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION audit_logs_guard()"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS audit_logs_guard ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_guard()")
