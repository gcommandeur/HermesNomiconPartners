"""Taegliche Faelligkeits-Mail (Auftrag "Notification-/Reminder-Engine").

Schickt jedem aktiven Nutzer EINE Sammel-Mail mit seinen heute faelligen/
ueberfaelligen Aufgaben und Prozess-Wiedervorlagen - nichts Faelliges, keine
Mail. Einstiegspunkt fuer einen DigitalOcean-App-Platform-"Scheduled Job"
(einmal taeglich morgens, siehe docs/DEPLOYMENT.md), gleiche Struktur wie
scripts/run_graph_sync.py. Ein Fehler bei EINEM Nutzer bricht den Lauf fuer
die uebrigen nicht ab; der Exit-Code ist 1, wenn mindestens ein Nutzer
fehlgeschlagen ist (damit der Job in der DO-Oberflaeche rot wird).

Usage (von backend/, mit aktivierter venv):

    python scripts/send_due_reminders.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.services.due_reminders import send_due_reminders  # noqa: E402


def main() -> int:
    with SessionLocal() as session:
        results = send_due_reminders(session)
    for result in results:
        suffix = f": {result.detail}" if result.detail else ""
        print(f"{result.email}: {result.outcome}{suffix}")
    sent = sum(1 for result in results if result.outcome == "sent")
    errors = sum(1 for result in results if result.outcome == "error")
    print(f"{sent} Erinnerung(en) versendet, {errors} Fehler, {len(results)} Nutzer geprueft.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
