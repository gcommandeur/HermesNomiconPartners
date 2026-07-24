"""Einmalige Bereinigung von Follow-up-Task-Duplikaten aus der Zeit VOR dem
Fix in services/submissions.py::transition() (siehe AUTO_FOLLOW_UP_DESCRIPTION
dort): der Fix schliesst bei jedem Statuswechsel automatisch die vorherigen
offenen automatischen Follow-ups, bevor ein neuer angelegt wird - wirkt aber
nur vorwaerts, ab dem Deploy des Fixes. Alle davor bereits automatisch
angelegten Follow-ups (z.B. "CV-Out nachfassen" UND "Interviewfeedback
nachfassen" gleichzeitig offen fuer denselben Prozess) blieben unangetastet
offen und erzeugen sichtbare Duplikate im "Fällig und überfällig"-Bereich der
Übersicht.

Kriterium fuer "automatisch erzeugt": exakter String-Match auf
description == AUTO_FOLLOW_UP_DESCRIPTION (siehe services/submissions.py) -
KEIN Fuzzy-Match auf den Titel, da der Titel je Prozessstufe variiert
("CV-Out nachfassen", "Interviewfeedback nachfassen", ...) und manuell vom
Nutzer angelegte Aufgaben zufaellig denselben Titel tragen koennten. Von
mehreren offenen automatischen Follow-ups pro candidate_submission_id bleibt
die zuletzt erstellte (created_at DESC) offen - das ist die zum aktuellen
Prozessstatus passende -, alle aelteren werden geschlossen.

Jeder automatisiert geschlossene Task bekommt einen Audit-Log-Eintrag
(entity_type "task", action "stale_followup_cleanup_closed") und einen
Vermerk in der description, damit im Nachhinein nachvollziehbar bleibt, dass
die Schliessung durch dieses Skript passiert ist, nicht durch einen
regulaeren Statuswechsel oder manuell durch einen Nutzer.

Dry-Run per Default - --apply fuer den echten Lauf.

Laeuft standardmaessig gegen die lokale DB aus CC_CRM_DATABASE_URL (.env).
Fuer Produktion (Managed PostgreSQL, siehe docs/DEPLOYMENT.md - lokale
SQLite-Dev-DB und Produktion sind seit dem Go-Live 2026-07-20 getrennte,
auseinandergelaufene Datenbestaende) --database-url mit der echten
Postgres-Connection-URL uebergeben, analog zu
migrate_sqlite_to_postgres.py --target-url. Dafuer muss vorab die eigene
IPv4 temporaer als Trusted Source am DB-Cluster hinterlegt werden (siehe
docs/DEPLOYMENT.md, Abschnitt "Datenbank").

Usage (aus backend/, mit aktiviertem venv):

    python scripts/cleanup_stale_followup_tasks.py
    python scripts/cleanup_stale_followup_tasks.py --apply
    python scripts/cleanup_stale_followup_tasks.py --database-url postgresql+psycopg://...
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.enums import TaskStatus  # noqa: E402
from cc_crm.models.submission import CandidateSubmission  # noqa: E402
from cc_crm.models.task import Task  # noqa: E402
from cc_crm.repositories.recruiting import AuditLogRepository  # noqa: E402
from cc_crm.repositories.tasks import TaskRepository  # noqa: E402
from cc_crm.services.submissions import AUTO_FOLLOW_UP_DESCRIPTION  # noqa: E402

CLEANUP_NOTE = (
    "\n\n[Automatisch geschlossen durch einmaliges Bereinigungs-Skript "
    "cleanup_stale_followup_tasks.py am {timestamp} - Alt-Duplikat von vor "
    "dem Fix in services/submissions.py::transition(), das seither "
    "vorherige automatische Follow-ups vor dem Anlegen eines neuen "
    "schliesst.]"
)


def _open_auto_follow_ups(session: Session) -> list[Task]:
    statement = select(Task).where(
        Task.description == AUTO_FOLLOW_UP_DESCRIPTION,
        Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
        Task.candidate_submission_id.isnot(None),
    )
    return list(session.scalars(statement).all())


def _group_by_submission(tasks: list[Task]) -> dict[uuid.UUID, list[Task]]:
    groups: dict[uuid.UUID, list[Task]] = defaultdict(list)
    for task in tasks:
        assert task.candidate_submission_id is not None
        groups[task.candidate_submission_id].append(task)
    return groups


def _label(session: Session, task: Task) -> str:
    # Task.candidate_id/client_company_id sind bei automatischen Follow-ups
    # normalerweise gesetzt (siehe services/submissions.py::transition()),
    # als Fallback aber ueber die zugehoerige Submission aufloesen, falls
    # doch mal leer.
    candidate_id = task.candidate_id
    client_company_id = task.client_company_id
    if (candidate_id is None or client_company_id is None) and task.candidate_submission_id:
        submission = session.get(CandidateSubmission, task.candidate_submission_id)
        if submission is not None:
            candidate_id = candidate_id or submission.candidate_id
            client_company_id = client_company_id or submission.client_company_id
    candidate = session.get(Candidate, candidate_id) if candidate_id else None
    client = session.get(ClientCompany, client_company_id) if client_company_id else None
    candidate_label = (
        f"{candidate.first_name} {candidate.last_name}" if candidate is not None else "?"
    )
    client_label = client.name if client is not None else "?"
    return f"{candidate_label} @ {client_label}"


def cleanup(*, apply: bool, database_url: str | None = None) -> dict[str, int]:
    session_factory: sessionmaker[Session]
    if database_url:
        engine = create_engine(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    else:
        session_factory = SessionLocal

    with session_factory() as session:
        open_tasks = _open_auto_follow_ups(session)
        groups = _group_by_submission(open_tasks)
        duplicate_groups = {
            submission_id: tasks for submission_id, tasks in groups.items() if len(tasks) > 1
        }

        submissions_affected = 0
        tasks_closed = 0
        tasks = TaskRepository(session)
        audit_logs = AuditLogRepository(session)
        now = datetime.now(UTC)

        for submission_id, group_tasks in duplicate_groups.items():
            ordered = sorted(group_tasks, key=lambda t: t.created_at, reverse=True)
            keep, stale = ordered[0], ordered[1:]
            submissions_affected += 1
            print(
                f"Submission {submission_id} ({_label(session, keep)}): "
                f"{len(group_tasks)} offene automatische Follow-ups, "
                f"{len(stale)} würde(n) geschlossen (behält '{keep.title}', "
                f"erstellt {keep.created_at.isoformat()})"
            )
            for stale_task in stale:
                action = "GESCHLOSSEN" if apply else "WÜRDE SCHLIESSEN"
                print(
                    f"  {action}: '{stale_task.title}' "
                    f"(fällig {stale_task.due_at}, erstellt {stale_task.created_at.isoformat()})"
                )
                tasks_closed += 1
                if apply:
                    old_status = stale_task.status.value
                    note = CLEANUP_NOTE.format(timestamp=now.isoformat())
                    tasks.update(
                        stale_task,
                        {
                            "status": TaskStatus.DONE,
                            "description": AUTO_FOLLOW_UP_DESCRIPTION + note,
                        },
                    )
                    audit_logs.create(
                        {
                            "entity_type": "task",
                            "entity_id": stale_task.id,
                            "action": "stale_followup_cleanup_closed",
                            "changed_at": now,
                            "changed_by": "cleanup_stale_followup_tasks.py",
                            "old_values": {"status": old_status},
                            "new_values": {
                                "status": TaskStatus.DONE.value,
                                "note": (
                                    "Alt-Duplikat vor dem Fix in "
                                    "services/submissions.py::transition() - "
                                    "einmalige Bereinigung"
                                ),
                            },
                        }
                    )

        if apply:
            session.commit()

        return {
            "submissions_checked": len(groups),
            "submissions_affected": submissions_affected,
            "tasks_closed": tasks_closed,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Tatsächlich schreiben (Default: Dry-Run)"
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "Optionale Ziel-DB (z.B. Produktions-Postgres statt lokaler "
            "CC_CRM_DATABASE_URL) - siehe Docstring oben."
        ),
    )
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    target = args.database_url or "lokale DB (CC_CRM_DATABASE_URL)"
    print(f"=== Follow-up-Duplikat-Bereinigung ({mode}) ===")
    print(f"Ziel-DB: {target}\n")
    stats = cleanup(apply=args.apply, database_url=args.database_url)

    print("\n=== Zusammenfassung ===")
    checked = stats["submissions_checked"]
    print(f"Submissions mit mind. 1 offenem automatischen Follow-up: {checked}")
    print(f"Davon mit Duplikaten (>1 offen): {stats['submissions_affected']}")
    print(f"Tasks geschlossen: {stats['tasks_closed']}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
