"""Einmaliges Backfill-Skript fuer Candidate.cv_available/cv_in_recorded_at
anhand bereits hochgeladener CV-Dokumente (Bugfix "CV-Dokument-Upload setzt
cv_available nicht", konkreter Fall: Lorenz Hafner - CV hochgeladen
2026-09-24, Flag nie gesetzt).

Hintergrund: DocumentService.create() stempelt cv_available/cv_in_
recorded_at jetzt bei jedem neuen CV-Dokument-Upload automatisch (siehe
services/operational.py::DocumentService._mark_cv_available_if_needed).
Dieses Skript holt die davor bereits hochgeladenen, aber nie nachgezogenen
Faelle nach: Kandidaten mit mindestens einem documents-Eintrag
(owner_type='candidate', document_type='cv') UND cv_available=False.
Live-Befund in Produktion (read-only Diagnose-Query): 9 betroffene
Kandidaten, alle nach dem 2026-07-15-Cutoff der Alt-Kandidaten-Ausnahme
angelegt (juengster 2026-09-24, aeltester 2026-07-27) - diese Ausnahme
selbst wird hier nicht angefasst, das Skript filtert nicht danach, prueft
aber implizit ueber die hochgeladenen Dokumente (Alt-Kandidaten aus dem
Datenuebertrag haben typischerweise keine echten Dokument-Uploads).

Setzt cv_available=True und (nur falls noch None - "einmalig, nie erneut
ueberschrieben", gleiches Prinzip wie CandidateService.update())
cv_in_recorded_at auf das FRUEHESTE documents.created_at des jeweiligen
CV-Dokuments (praeziserer Wert als candidate.created_at, da hier der
tatsaechliche Upload-Zeitpunkt bekannt ist).

Dry-Run per Default (zeigt nur an, was passieren wuerde), --commit fuer den
echten Lauf.

Usage (aus backend/, mit aktiviertem venv):

    python scripts/backfill_cv_available_from_documents.py
    python scripts/backfill_cv_available_from_documents.py --commit
"""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.operational import Document  # noqa: E402


@dataclass
class _Affected:
    candidate: Candidate
    earliest_cv_upload_at: datetime


def find_affected(session: Session) -> list[_Affected]:
    earliest_cv_upload_by_candidate: dict[uuid.UUID, datetime] = {
        row.owner_id: row[1]
        for row in session.execute(
            select(Document.owner_id, func.min(Document.created_at))
            .where(Document.owner_type == "candidate", Document.document_type == "cv")
            .group_by(Document.owner_id)
        ).all()
    }
    if not earliest_cv_upload_by_candidate:
        return []

    candidates = session.scalars(
        select(Candidate).where(
            Candidate.cv_available.is_(False),
            Candidate.id.in_(earliest_cv_upload_by_candidate.keys()),
        )
    ).all()
    return [
        _Affected(
            candidate=candidate,
            earliest_cv_upload_at=earliest_cv_upload_by_candidate[candidate.id],
        )
        for candidate in candidates
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit", action="store_true", help="Tatsaechlich schreiben (Default: nur anzeigen)."
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        affected = find_affected(session)
        print(
            f"{len(affected)} Kandidat(en) betroffen (hat mind. ein hochgeladenes "
            "CV-Dokument, aber cv_available=False):"
        )
        print()
        for item in affected:
            candidate = item.candidate
            print(
                f"  {candidate.candidate_number or '(keine Nr.)'} | "
                f"{candidate.first_name} {candidate.last_name} | "
                f"CV hochgeladen {item.earliest_cv_upload_at} | "
                f"cv_in_recorded_at bisher: {candidate.cv_in_recorded_at}"
            )

        if not args.commit:
            print()
            print("Dry-Run - nichts geschrieben. Mit --commit erneut ausfuehren.")
            return

        if not affected:
            print()
            print("Nichts zu tun.")
            return

        for item in affected:
            item.candidate.cv_available = True
            if item.candidate.cv_in_recorded_at is None:
                item.candidate.cv_in_recorded_at = item.earliest_cv_upload_at
        session.commit()

    print()
    print(f"Fertig: {len(affected)} Kandidat(en) nachbefuellt (cv_available=True).")


if __name__ == "__main__":
    main()
