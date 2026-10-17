# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Listet AKTIVE Einsaetze ohne gueltigen Ueberlassungsvertrag (nur lesend).

Seit der Vertragspruefung bei der Aktivierung (docs/UEBERLASSUNG.md) darf kein Einsatz mehr ohne
Vertrag aktiviert werden. Bereits aktive Altbestaende werden NICHT rueckwirkend veraendert; dieses
Skript zeigt, welche davon noch einen Vertrag brauchen. Es schreibt nichts (kein Commit) und gibt
keine Lohn- oder Margenwerte aus.

Usage (von backend/, mit aktivierter venv):

    python scripts/list_active_assignments_without_contract.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.staffing import StaffingAssignment, StaffingAssignmentStatus  # noqa: E402
from cc_crm.repositories.staffing import StaffingAssignmentRepository  # noqa: E402
from cc_crm.services.staffing_contract_sync import contract_problem_for  # noqa: E402


def main() -> int:
    today = date.today()
    with SessionLocal() as session:
        ids = session.scalars(
            select(StaffingAssignment.id).where(
                StaffingAssignment.status == StaffingAssignmentStatus.ACTIVE
            )
        ).all()
        repo = StaffingAssignmentRepository(session)
        findings = []
        for assignment_id in ids:
            row = repo.row(assignment_id)
            if row is None:
                continue
            problem = contract_problem_for(session, row.assignment, today)
            if problem is not None:
                findings.append((row, problem))
        session.rollback()  # nur lesen: nichts festschreiben
    for row, problem in sorted(findings, key=lambda f: (f[0].client_name, f[0].worker_name)):
        a = row.assignment
        end = a.planned_end_date.isoformat() if a.planned_end_date else "offen"
        print(
            f"{a.id}  {row.worker_name} bei {row.client_name}  {a.start_date.isoformat()} bis {end}"
        )
        print(f"    {problem}")
    print(f"{len(findings)} von {len(ids)} aktiven Einsaetzen ohne gueltigen Vertrag.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
