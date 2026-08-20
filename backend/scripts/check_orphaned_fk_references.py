"""Diagnose (READ-ONLY): verwaiste Fremdschluessel-Verweise ueber die gesamte
DB pruefen - Neufassung des fehlenden Teils von "Daten-Hygiene", nachdem der
urspruengliche Plan (hermes_datahygiene_kpi_prompt.md) nicht mehr auffindbar
war. Von der Recruiting-KPI-Haelfte des Plans getrennt (die ist fertig, siehe
CockpitService._recruiting_kpis). Die einzige bisherige Bereinigung
(cleanup_stale_followup_tasks.py) deckt nur Follow-up-Tasks ab, nicht die
uebrigen FK-Beziehungen im Schema.

Warum das ueberhaupt vorkommen kann, obwohl jede Spalte unten ein deklariertes
ondelete=... traegt: die Regel wird nur durchgesetzt, wenn (a) die Zeile ueber
eine SQL-DELETE-Anweisung verschwindet, bei der Postgres den Constraint
tatsaechlich prueft, UND (b) der Constraint zum Zeitpunkt des Loeschens auch
existierte. Kandidaten fuer Luecken: Zeilen aus der Zeit vor einer Migration,
die die Spalte/den Constraint erst nachtraeglich eingefuehrt hat, oder ein
Loeschpfad, der direkt gegen die DB lief statt ueber die ORM-Session (z.B.
manuelle Korrekturen wie im Bereinigungs-Skript oben referenziert:
Kandidaten-/Kanzlei-Loeschungen, als Prozess mit Grund "Fehler" geloescht).

Schritt 1 (Bestandsaufnahme) ist die Liste _CHECKS unten - jede Zeile ein
Fund aus `grep -rn "ForeignKey(" backend/src/cc_crm/models/`. Zwei Spalten
sind absichtlich NICHT als deklarierte ForeignKey angelegt und daher separat
behandelt (siehe _polymorphic Abschnitt unten):
- Document.owner_id (polymorphisch ueber owner_type, siehe models/operational.py)
- AuditLog.entity_id (polymorphisch ueber entity_type - bewusst OHNE Pruefung
  hier: ein Audit-Log-Eintrag zu einer laengst geloeschten Zeile ist gewollt,
  kein Datenfehler, das Log soll gerade UEBER die Loeschung hinaus bestehen
  bleiben)

Schritt 2 ist dieses Skript: fuer jede FK-Spalte zaehlt es Zeilen, deren Wert
gesetzt ist, aber in der Zielspalte keine passende id mehr existiert
(reines COUNT/Beispiel-IDs per NOT EXISTS-Subquery - keine Aenderung, kein
DELETE, kein UPDATE).

Schritt 3 (was mit Funden passiert - auf NULL setzen/loeschen/stehen lassen)
ist NICHT Teil dieses Skripts, folgt erst nach gemeinsamer Sichtung der
Ergebnisse.

Laeuft standardmaessig gegen die lokale DB aus CC_CRM_DATABASE_URL (.env).
Fuer Produktion (Managed PostgreSQL) --database-url mit der echten
Postgres-Connection-URL uebergeben, analog zu
cleanup_stale_followup_tasks.py --database-url (dafuer vorab die eigene IPv4
temporaer als Trusted Source am DB-Cluster hinterlegen, siehe
docs/DEPLOYMENT.md, Abschnitt "Datenbank").

Usage (aus backend/, mit aktiviertem venv):

    python scripts/check_orphaned_fk_references.py
    python scripts/check_orphaned_fk_references.py --database-url postgresql+psycopg://...
    python scripts/check_orphaned_fk_references.py --examples 10
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from cc_crm.infrastructure.database.session import engine as _local_engine  # noqa: E402


@dataclass(frozen=True)
class FkCheck:
    table: str
    column: str
    ref_table: str
    ondelete: str
    # Bei CASCADE/RESTRICT sollte die DB einen verwaisten Zustand eigentlich
    # gar nicht erst zulassen - trotzdem mitgeprueft (Sanity-Check: falls
    # doch was auftaucht, ist das ein staerkeres Warnsignal als bei SET NULL).
    nullable: bool = True


# Schritt 1: vollstaendige Bestandsaufnahme aus `grep -rn "ForeignKey(" models/`.
# Reihenfolge wie in den Modell-Dateien, gruppiert nach Quelltabelle.
_CHECKS: list[FkCheck] = [
    # user.py
    FkCheck("users", "default_send_account_id", "mail_accounts", "SET NULL"),
    # api_key.py
    FkCheck("api_keys", "user_id", "users", "CASCADE", nullable=False),
    # operational.py
    FkCheck("documents", "sent_with_submission_id", "candidate_submissions", "SET NULL"),
    FkCheck("email_draft_logs", "candidate_id", "candidates", "SET NULL"),
    FkCheck("email_draft_logs", "client_company_id", "client_companies", "SET NULL"),
    FkCheck("email_draft_logs", "candidate_submission_id", "candidate_submissions", "SET NULL"),
    # sourcing_lead.py
    FkCheck("sourcing_leads", "matched_client_company_id", "client_companies", "SET NULL"),
    FkCheck("sourcing_leads", "duplicate_of_candidate_id", "candidates", "SET NULL"),
    FkCheck("sourcing_leads", "created_candidate_id", "candidates", "SET NULL"),
    FkCheck("sourcing_leads", "reviewed_by_user_id", "users", "SET NULL"),
    # calendar_event.py
    FkCheck("calendar_events", "owner_user_id", "users", "CASCADE", nullable=False),
    FkCheck("calendar_events", "created_by_user_id", "users", "CASCADE", nullable=False),
    FkCheck("calendar_events", "candidate_id", "candidates", "SET NULL"),
    FkCheck("calendar_events", "client_company_id", "client_companies", "SET NULL"),
    FkCheck("calendar_events", "candidate_submission_id", "candidate_submissions", "SET NULL"),
    FkCheck("calendar_events", "source_interview_id", "interviews", "CASCADE"),
    # activity.py
    FkCheck("activities", "candidate_id", "candidates", "CASCADE"),
    FkCheck("activities", "client_company_id", "client_companies", "CASCADE"),
    FkCheck("activities", "candidate_submission_id", "candidate_submissions", "CASCADE"),
    # auth.py
    FkCheck("auth_sessions", "user_id", "users", "CASCADE", nullable=False),
    # note.py
    FkCheck("notes", "candidate_id", "candidates", "CASCADE"),
    FkCheck("notes", "client_company_id", "client_companies", "CASCADE"),
    FkCheck("notes", "candidate_submission_id", "candidate_submissions", "CASCADE"),
    # task.py
    FkCheck("tasks", "candidate_id", "candidates", "CASCADE"),
    FkCheck("tasks", "client_company_id", "client_companies", "CASCADE"),
    FkCheck("tasks", "candidate_submission_id", "candidate_submissions", "CASCADE"),
    FkCheck("tasks", "owner_user_id", "users", "SET NULL"),
    FkCheck("tasks", "source_mail_message_id", "mail_messages", "SET NULL"),
    # submission.py
    FkCheck("candidate_submissions", "candidate_id", "candidates", "RESTRICT", nullable=False),
    FkCheck("candidate_submissions", "client_company_id", "client_companies", "RESTRICT"),
    FkCheck("candidate_submissions", "job_mandate_id", "job_mandates", "SET NULL"),
    FkCheck("candidate_submissions", "contact_person_id", "contact_persons", "SET NULL"),
    FkCheck("candidate_submissions", "owner_user_id", "users", "SET NULL"),
    # client_company.py
    FkCheck("client_companies", "owner_user_id", "users", "SET NULL"),
    # mail.py
    FkCheck("mail_messages", "mail_account_id", "mail_accounts", "CASCADE", nullable=False),
    FkCheck("mail_messages", "matched_candidate_id", "candidates", "SET NULL"),
    FkCheck("mail_messages", "matched_contact_person_id", "contact_persons", "SET NULL"),
    FkCheck("mail_messages", "matched_client_company_id", "client_companies", "SET NULL"),
    FkCheck("mail_messages", "created_activity_id", "activities", "SET NULL"),
    # job_mandate.py
    FkCheck("job_mandates", "client_company_id", "client_companies", "RESTRICT", nullable=False),
    # recruiting.py
    FkCheck(
        "submission_feedback", "submission_id", "candidate_submissions", "CASCADE", nullable=False
    ),
    FkCheck("interviews", "submission_id", "candidate_submissions", "CASCADE", nullable=False),
    FkCheck("offers", "submission_id", "candidate_submissions", "CASCADE", nullable=False),
    FkCheck("placements", "submission_id", "candidate_submissions", "RESTRICT", nullable=False),
    FkCheck("fees", "placement_id", "placements", "CASCADE", nullable=False),
    # contact_person.py
    FkCheck("contact_persons", "client_company_id", "client_companies", "CASCADE", nullable=False),
    # candidate.py
    FkCheck("candidates", "owner_user_id", "users", "SET NULL"),
]


# Polymorphe Verweise ohne deklarierten FK-Constraint - separat, weil die DB
# hier grundsaetzlich nichts durchsetzen kann (kein Constraint moeglich bei
# einem Ziel, das je nach owner_type wechselt). AuditLog.entity_id ist
# ABSICHTLICH ausgenommen (siehe Modul-Docstring oben).
_POLYMORPHIC_OWNER_TABLES = {
    "candidate": "candidates",
    "client_company": "client_companies",
}


def _redact_url(database_url: str) -> str:
    if "@" not in database_url or "://" not in database_url:
        return database_url
    scheme, rest = database_url.split("://", 1)
    credentials, host_part = rest.split("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host_part}"


def _check_one(engine: Engine, check: FkCheck, *, example_limit: int) -> tuple[int, list[str]]:
    count_sql = text(
        f"""
        SELECT COUNT(*) FROM {check.table} t
        WHERE t.{check.column} IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM {check.ref_table} r WHERE r.id = t.{check.column})
        """
    )
    examples_sql = text(
        f"""
        SELECT t.id FROM {check.table} t
        WHERE t.{check.column} IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM {check.ref_table} r WHERE r.id = t.{check.column})
        LIMIT :n
        """
    )
    with engine.connect() as conn:
        count = conn.execute(count_sql).scalar_one()
        examples = [str(row[0]) for row in conn.execute(examples_sql, {"n": example_limit})]
    return count, examples


def _check_polymorphic_documents(engine: Engine, *, example_limit: int) -> tuple[int, list[str]]:
    """documents.owner_id ist nur gueltig, wenn die Zeile in der zu
    owner_type passenden Tabelle existiert - je nach owner_type eine andere
    Zieltabelle, daher UNION statt einer einzelnen NOT EXISTS-Subquery."""
    clauses = " AND\n          ".join(
        f"NOT (t.owner_type = '{owner_type}' AND EXISTS "
        f"(SELECT 1 FROM {ref_table} r WHERE r.id = t.owner_id))"
        for owner_type, ref_table in _POLYMORPHIC_OWNER_TABLES.items()
    )
    known_types = ", ".join(f"'{t}'" for t in _POLYMORPHIC_OWNER_TABLES)
    count_sql = text(
        f"""
        SELECT COUNT(*) FROM documents t
        WHERE t.owner_type IN ({known_types}) AND
          {clauses}
        """
    )
    examples_sql = text(
        f"""
        SELECT t.id FROM documents t
        WHERE t.owner_type IN ({known_types}) AND
          {clauses}
        LIMIT :n
        """
    )
    with engine.connect() as conn:
        count = conn.execute(count_sql).scalar_one()
        examples = [str(row[0]) for row in conn.execute(examples_sql, {"n": example_limit})]
    return count, examples


def run(*, database_url: str | None, example_limit: int) -> list[dict[str, object]]:
    engine = create_engine(database_url) if database_url else _local_engine

    results: list[dict[str, object]] = []
    for check in _CHECKS:
        count, examples = _check_one(engine, check, example_limit=example_limit)
        results.append(
            {
                "table": check.table,
                "column": check.column,
                "ref_table": check.ref_table,
                "ondelete": check.ondelete,
                "count": count,
                "examples": examples,
            }
        )

    doc_count, doc_examples = _check_polymorphic_documents(engine, example_limit=example_limit)
    results.append(
        {
            "table": "documents",
            "column": "owner_id (polymorph ueber owner_type)",
            "ref_table": "candidates/client_companies",
            "ondelete": "n/a (kein DB-Constraint moeglich)",
            "count": doc_count,
            "examples": doc_examples,
        }
    )
    return results


def _print_report(results: list[dict[str, object]]) -> None:
    affected = [row for row in results if row["count"]]

    print(f"{len(_CHECKS) + 1} FK-Beziehungen geprueft.\n")

    if not affected:
        print("Keine verwaisten Verweise gefunden - alle Fremdschluessel sind sauber.")
        return

    print(f"{len(affected)} Beziehung(en) mit verwaisten Verweisen:\n")
    header = f"{'Tabelle':<24} {'Spalte':<38} {'Ziel':<22} {'ondelete':<10} {'Anzahl':>7}"
    print(header)
    print("-" * len(header))
    for row in affected:
        print(
            f"{row['table']:<24} {row['column']:<38} {row['ref_table']:<22} "
            f"{row['ondelete']:<10} {row['count']:>7}"
        )
        examples = ", ".join(row["examples"])  # type: ignore[arg-type]
        print(f"    Beispiel-IDs: {examples}")
    print()
    print(
        "Schritt 3 (auf NULL setzen / loeschen / bewusst stehen lassen) ist "
        "NICHT Teil dieses Laufs - erst nach gemeinsamer Sichtung."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optionale Ziel-DB (z.B. Produktions-Postgres statt lokaler CC_CRM_DATABASE_URL).",
    )
    parser.add_argument(
        "--examples", type=int, default=5, help="Max. Beispiel-IDs je Fund (Default: 5)"
    )
    args = parser.parse_args()

    target = (
        _redact_url(args.database_url) if args.database_url else "lokale DB (CC_CRM_DATABASE_URL)"
    )
    print("=== Verwaiste FK-Verweise (READ-ONLY Diagnose) ===")
    print(f"Ziel-DB: {target}\n")

    results = run(database_url=args.database_url, example_limit=args.examples)
    _print_report(results)


if __name__ == "__main__":
    main()
