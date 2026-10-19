# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Taeglicher Job: Aufgaben fuer ablaufende Ueberlassungsfristen und Erlaubnisse.

Einstiegspunkt fuer einen DigitalOcean-"Scheduled Job" (einmal taeglich, z. B. `30 5 * * *` UTC,
vor dem Versand der Faelligkeits-Mails), gleiche Struktur wie scripts/send_due_reminders.py.
Idempotent: je Paar und Schwelle entsteht genau eine Aufgabe.

Usage (von backend/, mit aktivierter venv):

    python scripts/run_staffing_deadlines.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.services.staffing_deadline_job import run_deadline_job  # noqa: E402


def main() -> int:
    with SessionLocal() as session:
        result = run_deadline_job(session)
    print(f"{result.pairs_checked} Paar(e) geprueft, {result.tasks_created} Aufgabe(n) angelegt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
