"""Einmalige Bereinigung von Follow-up-Task-Altlasten aus der Zeit VOR dem
Fix in services/submissions.py::transition() (siehe AUTO_FOLLOW_UP_DESCRIPTION
dort): der Fix schliesst bei jedem Statuswechsel (auch bei CANCELLED)
automatisch alle vorherigen offenen automatischen Follow-ups, bevor ein neuer
angelegt wird - wirkt aber nur vorwaerts, ab dem Deploy des Fixes. Dieses
Skript deckt drei Arten von Altlasten ab, die davor entstanden sind und
seither unangetastet offen blieben:

1. DUPLIKATE: mehrere offene automatische Follow-ups fuer dieselbe
   Submission (z.B. "CV-Out nachfassen" UND "Interviewfeedback nachfassen"
   gleichzeitig offen). Es bleibt die zuletzt erstellte (created_at DESC)
   offen, aeltere werden geschlossen.
2. GEGENSTANDSLOS (Prozess abgebrochen): die verknuepfte Submission steht
   auf CANCELLED - der Follow-up ist damit hinfaellig, wird aber vom
   Duplikat-Check allein nicht erfasst, wenn es der einzige offene
   automatische Follow-up dieser Submission ist (kein Duplikat, aber trotzdem
   veraltet). Alle offenen automatischen Follow-ups einer abgebrochenen
   Submission werden geschlossen.
3. VERWAIST: candidate_submission_id ist leer (oder verweist auf eine nicht
   mehr existierende Submission) - es gibt keinen Bezug mehr, ueber den sich
   Kandidat/Kanzlei auflösen liesse, der Task ist nicht mehr aktionabel.

Kriterium fuer "automatisch erzeugt": exakter String-Match auf
description == AUTO_FOLLOW_UP_DESCRIPTION (siehe services/submissions.py) -
KEIN Fuzzy-Match auf den Titel, da der Titel je Prozessstufe variiert
("CV-Out nachfassen", "Interviewfeedback nachfassen", ...) und manuell vom
Nutzer angelegte Aufgaben zufaellig denselben Titel tragen koennten.

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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.enums import SubmissionStatus, TaskStatus  # noqa: E402
from cc_crm.models.submission import CandidateSubmission  # noqa: E402
from cc_crm.models.task import Task  # noqa: E402
from cc_crm.repositories.recruiting import AuditLogRepository  # noqa: E402
from cc_crm.repositories.tasks import TaskRepository  # noqa: E402
from cc_crm.services.submissions import AUTO_FOLLOW_UP_DESCRIPTION  # noqa: E402

CLEANUP_NOTE = (
    "\n\n[Automatisch geschlossen durch einmaliges Bereinigungs-Skript "
    "cleanup_stale_followup_tasks.py am {timestamp} - {reason}]"
)

REASON_DUPLICATE = (
    "Alt-Duplikat von vor dem Fix in services/submissions.py::transition(), "
    "das seither vorherige automatische Follow-ups vor dem Anlegen eines "
    "neuen schliesst."
)
REASON_CANCELLED = "Prozess ist abgebrochen (cancelled) - Follow-up ist hinfaellig."
REASON_ORPHANED = "Follow-up ohne (mehr) gueltigen Prozessbezug (candidate_submission_id leer)."


def _redact_url(database_url: str) -> str:
    """Passwort in einer Connection-URL fuer Logs/Print-Ausgaben maskieren -
    Produktions-Zugangsdaten sollen unter keinen Umstaenden in Terminal-
    Output oder Skript-Logs landen."""
    if "@" not in database_url or "://" not in database_url:
        return database_url
    scheme, rest = database_url.split("://", 1)
    credentials, host_part = rest.split("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host_part}"


def _open_auto_follow_ups(session: Session) -> list[Task]:
    statement = select(Task).where(
        Task.description == AUTO_FOLLOW_UP_DESCRIPTION,
        Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
    )
    return list(session.scalars(statement).all())


def _label(session: Session, task: Task, submission: CandidateSubmission | None) -> str:
    # Task.candidate_id/client_company_id sind bei automatischen Follow-ups
    # normalerweise gesetzt (siehe services/submissions.py::transition()),
    # als Fallback aber ueber die zugehoerige Submission aufloesen, falls
    # doch mal leer.
    candidate_id = task.candidate_id or (submission.candidate_id if submission else None)
    client_company_id = task.client_company_id or (
        submission.client_company_id if submission else None
    )
    candidate = session.get(Candidate, candidate_id) if candidate_id else None
    client = session.get(ClientCompany, client_company_id) if client_company_id else None
    candidate_label = (
        f"{candidate.first_name} {candidate.last_name}" if candidate is not None else "?"
    )
    client_label = client.name if client is not None else "?"
    return f"{candidate_label} @ {client_label}"


def _close_task(
    session: Session,
    tasks: TaskRepository,
    audit_logs: AuditLogRepository,
    task: Task,
    *,
    apply: bool,
    reason: str,
    now: datetime,
) -> None:
    if not apply:
        return
    tasks.update(
        task,
        {
            "status": TaskStatus.DONE,
            "description": AUTO_FOLLOW_UP_DESCRIPTION
            + CLEANUP_NOTE.format(timestamp=now.isoformat(), reason=reason),
        },
    )
    audit_logs.create(
        {
            "entity_type": "task",
            "entity_id": task.id,
            "action": "stale_followup_cleanup_closed",
            "changed_at": now,
            "changed_by": "cleanup_stale_followup_tasks.py",
            "old_values": {"status": task.status.value},
            "new_values": {"status": TaskStatus.DONE.value, "note": reason},
        }
    )


def cleanup(*, apply: bool, database_url: str | None = None) -> dict[str, int]:
    session_factory: sessionmaker[Session]
    if database_url:
        engine = create_engine(database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    else:
        session_factory = SessionLocal

    with session_factory() as session:
        open_tasks = _open_auto_follow_ups(session)
        submission_ids = {
            task.candidate_submission_id for task in open_tasks if task.candidate_submission_id
        }
        submissions = {
            item.id: item
            for item in session.scalars(
                select(CandidateSubmission).where(CandidateSubmission.id.in_(submission_ids))
            ).all()
        }

        orphaned: list[Task] = []
        moot: list[Task] = []
        active_by_submission: dict[uuid.UUID, list[Task]] = defaultdict(list)

        for task in open_tasks:
            submission = (
                submissions.get(task.candidate_submission_id)
                if task.candidate_submission_id
                else None
            )
            if submission is None:
                orphaned.append(task)
            elif submission.status == SubmissionStatus.CANCELLED:
                moot.append(task)
            else:
                active_by_submission[submission.id].append(task)

        duplicate_groups = {
            submission_id: tasks
            for submission_id, tasks in active_by_submission.items()
            if len(tasks) > 1
        }

        tasks_repo = TaskRepository(session)
        audit_logs = AuditLogRepository(session)
        now = datetime.now(UTC)
        duplicates_closed = 0
        moot_closed = 0
        orphaned_closed = 0

        if duplicate_groups:
            print("--- Duplikate (mehrere offene automatische Follow-ups pro Prozess) ---")
        for submission_id, group_tasks in duplicate_groups.items():
            ordered = sorted(group_tasks, key=lambda t: t.created_at, reverse=True)
            keep, stale = ordered[0], ordered[1:]
            submission = submissions.get(submission_id)
            print(
                f"Submission {submission_id} ({_label(session, keep, submission)}): "
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
                duplicates_closed += 1
                _close_task(
                    session, tasks_repo, audit_logs, stale_task,
                    apply=apply, reason=REASON_DUPLICATE, now=now,
                )

        if moot:
            print("\n--- Gegenstandslos (Prozess abgebrochen) ---")
        for task in moot:
            submission = (
                submissions.get(task.candidate_submission_id)
                if task.candidate_submission_id
                else None
            )
            action = "GESCHLOSSEN" if apply else "WÜRDE SCHLIESSEN"
            print(
                f"{action}: '{task.title}' ({_label(session, task, submission)}) "
                f"(fällig {task.due_at}, erstellt {task.created_at.isoformat()})"
            )
            moot_closed += 1
            _close_task(
                session, tasks_repo, audit_logs, task,
                apply=apply, reason=REASON_CANCELLED, now=now,
            )

        if orphaned:
            print("\n--- Verwaist (kein Prozessbezug mehr) ---")
        for task in orphaned:
            action = "GESCHLOSSEN" if apply else "WÜRDE SCHLIESSEN"
            print(
                f"{action}: '{task.title}' (fällig {task.due_at}, "
                f"erstellt {task.created_at.isoformat()})"
            )
            orphaned_closed += 1
            _close_task(
                session, tasks_repo, audit_logs, task,
                apply=apply, reason=REASON_ORPHANED, now=now,
            )

        if apply:
            session.commit()

        return {
            "duplicates_closed": duplicates_closed,
            "moot_closed": moot_closed,
            "orphaned_closed": orphaned_closed,
            "tasks_closed": duplicates_closed + moot_closed + orphaned_closed,
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
    if args.database_url:
        target = _redact_url(args.database_url)
    else:
        target = "lokale DB (CC_CRM_DATABASE_URL)"
    print(f"=== Follow-up-Altlasten-Bereinigung ({mode}) ===")
    print(f"Ziel-DB: {target}\n")
    stats = cleanup(apply=args.apply, database_url=args.database_url)

    print("\n=== Zusammenfassung ===")
    print(f"Duplikate geschlossen: {stats['duplicates_closed']}")
    print(f"Gegenstandslos (abgebrochen) geschlossen: {stats['moot_closed']}")
    print(f"Verwaist geschlossen: {stats['orphaned_closed']}")
    print(f"Insgesamt geschlossen: {stats['tasks_closed']}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
