"""Rueckwirkendes Backfill: legt fuer alle bestehenden interviews-Datensaetze
OHNE zugehoerigen calendar_events-Eintrag (source_interview_id noch nicht
gesetzt) einen Kalendereintrag nach derselben Logik wie
services/recruiting.py::RecruitingProcessService._create_calendar_event_for_interview
an (Titel, Erinnerung, Verknuepfung zu Kandidat/Kanzlei/Prozess).

Bei diesen historischen Faellen ist NICHT bekannt, wer das Interview
urspruenglich angelegt hat (die automatische Kalender-Erstellung bei
create_interview kam erst spaeter dazu) - owner_user_id/created_by_user_id
werden deshalb bewusst auf den Admin-Nutzer info@commandeurconsulting.de
gesetzt, nicht auf einen beliebigen/erratenen Nutzer.

Idempotent: ein Interview, das bereits einen verknuepften Kalendereintrag hat
(egal von wem/wann erzeugt), wird uebersprungen - mehrfacher Aufruf erzeugt
keine Duplikate.

Usage (von backend/, mit aktiviertem venv):

    python scripts/backfill_calendar_events_for_interviews.py
    python scripts/backfill_calendar_events_for_interviews.py --dry-run
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.recruiting import Interview  # noqa: E402
from cc_crm.models.submission import CandidateSubmission  # noqa: E402
from cc_crm.models.user import User  # noqa: E402
from cc_crm.repositories.calendar_events import CalendarEventRepository  # noqa: E402
from cc_crm.services.recruiting import RecruitingProcessService  # noqa: E402

ADMIN_EMAIL = "info@commandeurconsulting.de"


def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]

    with SessionLocal() as session:
        admin = session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if admin is None:
            print(f"Admin-Nutzer {ADMIN_EMAIL} nicht gefunden - Abbruch.")
            raise SystemExit(1)

        calendar_events = CalendarEventRepository(session)
        recruiting = RecruitingProcessService(session)

        interviews = session.scalars(select(Interview)).all()
        created = 0
        skipped = 0
        failed = 0

        for interview in interviews:
            if calendar_events.for_source_interview(interview.id) is not None:
                skipped += 1
                continue

            submission = session.get(CandidateSubmission, interview.submission_id)
            if submission is None:
                # Verwaistes Interview (Submission geloescht) - nichts anzulegen.
                skipped += 1
                continue

            if dry_run:
                print(f"[dry-run] wuerde Kalendereintrag anlegen fuer Interview {interview.id}")
                created += 1
                continue

            try:
                recruiting._create_calendar_event_for_interview(  # noqa: SLF001
                    interview, submission, admin
                )
                created += 1
            except Exception as exception:  # noqa: BLE001
                failed += 1
                print(f"Fehlgeschlagen fuer Interview {interview.id}: {exception}")

        print(
            f"Fertig: {created} Kalendereintraege angelegt, "
            f"{skipped} bereits vorhanden/uebersprungen, {failed} fehlgeschlagen."
        )


if __name__ == "__main__":
    main()
