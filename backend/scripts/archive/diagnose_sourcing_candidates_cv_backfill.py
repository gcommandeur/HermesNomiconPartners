"""READ-ONLY Diagnose: wie viele Kandidaten stammen aus dem Sourcing-Agent
(SourcingLead -> approve_lead -> CandidateService.create(), siehe
services/sourcing.py) statt aus einem hochgeladenen CV, und wo stehen sie?

Diese Kandidaten sind ueber KEIN "Herkunft"-Feld markiert - approve_lead()
setzt beim Anlegen nur first_name/last_name/city/postal_code/summary/
owner_user_id, sonst nichts Unterscheidbares. Die einzige verlaessliche
Verknuepfung ist SourcingLead.created_candidate_id (gesetzt genau dort, wo
approve_lead() den Kandidaten erzeugt hat), kombiniert mit
status='approved' (der einzige Status, der ueberhaupt zu einem Kandidaten
fuehrt - siehe SourcingLeadStatus-Docstring).

Relevanz fuer den CV-Rollen-Backfill (backfill_cv_rollen_und_schwerpunkte.py):
approve_lead() erzeugt NIE ein Document (nur ggf. eine Note aus
lead.notes_text) - ein CV-basierter Re-Parse kann bei diesen Kandidaten
strukturell nichts liefern, solange sie kein eigenes CV nachgereicht haben.

Schreibt/aendert NICHTS - reine Bestandsaufnahme.

Usage (aus backend/, mit aktiviertem venv):

    python scripts/diagnose_sourcing_candidates_cv_backfill.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.enums import SourcingLeadStatus  # noqa: E402
from cc_crm.models.operational import Document  # noqa: E402
from cc_crm.models.sourcing_lead import SourcingLead  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "sourcing_candidates_cv_backfill_diagnose.csv"

CSV_FIELDS = [
    "candidate_number",
    "candidate_id",
    "sourcing_found_at",
    "candidate_created_at",
    "source_type",
    "hat_cv_dokument",
    "job_title_gesetzt",
    "current_employer_internal_gesetzt",
    "rollen_gesetzt",
]


def diagnose() -> None:
    with SessionLocal() as session:
        pairs = session.execute(
            select(Candidate, SourcingLead)
            .join(SourcingLead, SourcingLead.created_candidate_id == Candidate.id)
            .where(SourcingLead.status == SourcingLeadStatus.APPROVED)
            .order_by(Candidate.candidate_number)
        ).all()

        rows: list[dict[str, str]] = []
        candidates_with_cv = 0

        for candidate, lead in pairs:
            has_cv = (
                session.scalar(
                    select(Document.id).where(
                        Document.owner_type == "candidate",
                        Document.owner_id == candidate.id,
                        Document.document_type == "cv",
                    )
                )
                is not None
            )
            if has_cv:
                candidates_with_cv += 1

            rows.append(
                {
                    "candidate_number": candidate.candidate_number or "",
                    "candidate_id": str(candidate.id),
                    "sourcing_found_at": lead.found_at.isoformat() if lead.found_at else "",
                    "candidate_created_at": candidate.created_at.isoformat()
                    if candidate.created_at
                    else "",
                    "source_type": lead.source_type.value if lead.source_type else "",
                    "hat_cv_dokument": "ja" if has_cv else "nein",
                    "job_title_gesetzt": "ja" if candidate.job_title else "nein",
                    "current_employer_internal_gesetzt": "ja"
                    if candidate.current_employer_internal
                    else "nein",
                    "rollen_gesetzt": "ja" if candidate.rollen else "nein",
                }
            )

    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print("=== Sourcing-Agent-Kandidaten: Diagnose fuer den CV-Rollen-Backfill ===")
    print(f"Insgesamt gefunden: {len(rows)}")
    if rows:
        numbers = [
            int(r["candidate_number"]) for r in rows if str(r["candidate_number"]).isdigit()
        ]
        if numbers:
            print(f"candidate_number-Spanne: {min(numbers)} - {max(numbers)}")
        found_dates = sorted(r["sourcing_found_at"] for r in rows if r["sourcing_found_at"])
        if found_dates:
            print(f"sourcing_lead.found_at-Spanne: {found_dates[0]} - {found_dates[-1]}")
        created_dates = sorted(r["candidate_created_at"] for r in rows if r["candidate_created_at"])
        if created_dates:
            print(f"candidate.created_at-Spanne: {created_dates[0]} - {created_dates[-1]}")
    print(f"Davon MIT CV-Dokument (werden NICHT ausgeschlossen): {candidates_with_cv}")
    print(
        f"Davon OHNE CV-Dokument (Ausschlusskandidaten fuer den Backfill): "
        f"{len(rows) - candidates_with_cv}"
    )
    print(f"\nDiagnose-CSV: {OUTPUT_PATH}")


if __name__ == "__main__":
    diagnose()
