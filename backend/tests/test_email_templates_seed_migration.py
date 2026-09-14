"""Verifiziert die Seed-Daten der Migration d4e5f6a7b8c9 (Auftrag "Mailvorlagen
editierbar machen"): 13 bestehende + 12 neue Vorlagen = 25 Zeilen in
`email_templates`, jede mit eindeutigem `key`.

Der normale pytest-`session_factory`-Fixture (siehe conftest.py) baut die
Test-DB per `Base.metadata.create_all()` direkt aus den Modellen auf, OHNE
die Alembic-Migrationen auszufuehren - die Seed-Daten aus `op.bulk_insert()`
waeren dort also nie vorhanden. Dieser Test laesst deshalb die echte Migration
gegen eine frische temporaere SQLite-Datei laufen (wie `alembic upgrade head`
in der DO-Console), statt die Migrationsmechanik zu umgehen."""

import uuid
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from cc_crm.core.config import get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_EXISTING_KEYS = {
    "post_qualification_call",
    "request_cv",
    "profile_approval",
    "candidate_submission",
    "submission_follow_up",
    "interview_confirmation",
    "interview_feedback",
    "interview_feedback_candidate",
    "offer_follow_up",
    "candidate_rejection",
    "client_rejection",
    "send_terms",
    "placement_invoice",
}

EXPECTED_NEW_KEYS = {
    "cv_blind_submission",
    "candidate_availability_note",
    "candidate_intro_longform",
    "candidate_options_intro",
    "call_follow_up",
    "vacancy_pitch_to_candidate",
    "interview_scheduling_proposal",
    "client_feedback_request",
    "contract_dispatch",
    "pending_response_reminder",
    "client_rejection_update_to_candidate",
    "gdpr_consent_request",
}


def test_migration_seeds_13_existing_plus_12_new_templates(
    tmp_path: Path, monkeypatch: object
) -> None:
    db_path = tmp_path / "email_templates_seed_check.sqlite3"
    monkeypatch.setenv("CC_CRM_DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    get_settings.cache_clear()
    try:
        alembic_cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(f"sqlite+pysqlite:///{db_path}")
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT id, key, name, subject, body FROM email_templates")
            ).all()
        engine.dispose()
    finally:
        get_settings.cache_clear()

    assert len(rows) == 25
    keys = [row.key for row in rows]
    assert len(set(keys)) == 25, "keys must be unique"
    assert set(keys) == EXPECTED_EXISTING_KEYS | EXPECTED_NEW_KEYS

    for row in rows:
        # jede Zeile hat eine echte UUID-PK, einen nicht-leeren Namen/Betreff/
        # Text (keine leeren Platzhalter-Zeilen).
        assert uuid.UUID(str(row.id))
        assert row.name.strip()
        assert row.subject.strip()
        assert row.body.strip()
