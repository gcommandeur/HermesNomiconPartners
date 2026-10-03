"""Taeglicher Lauf der Outreach-Sequenzen (Auftrag "Mehrkanal-Outreach-Sequenzen").

Fuehrt fuer jede laufende Einschreibung den faelligen Schritt aus (E-Mail wird
versendet, alle anderen Kanaele legen einen Task an) und pausiert Einschreibungen,
sobald der Kandidat geantwortet hat. Einstiegspunkt fuer einen DigitalOcean-
App-Platform-"Scheduled Job" (einmal taeglich morgens, siehe docs/DEPLOYMENT.md),
gleiche Struktur wie scripts/run_graph_sync.py und scripts/send_due_reminders.py.
Mehrfacher Aufruf am selben Tag ist unschaedlich (hoechstens ein Schritt pro Tag
und Einschreibung). Ein Fehler bei EINER Einschreibung stoppt die anderen nicht;
Exit-Code 1, wenn mindestens eine fehlgeschlagen ist.

Usage (von backend/, mit aktivierter venv):

    python scripts/run_outreach_sequences.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.services.outreach_sequences import run_due_steps  # noqa: E402


def main() -> int:
    with SessionLocal() as session:
        results = run_due_steps(session)
    for result in results:
        if result.outcome == "not_due":
            continue
        suffix = f": {result.detail}" if result.detail else ""
        print(f"Einschreibung {result.enrollment_id}: {result.outcome}{suffix}")
    errors = sum(1 for result in results if result.outcome == "error")
    executed = sum(1 for result in results if result.outcome.startswith("executed"))
    print(
        f"{len(results)} Einschreibung(en) geprueft, "
        f"{executed} Schritt(e) ausgefuehrt, {errors} Fehler."
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
