# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Dummy-Daten der Ueberlassung (scripts/seed_staffing.py) laufen durch die echten Regeln."""

import random
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingChecklistItem,
    StaffingContract,
    StaffingLicense,
    StaffingWorker,
    StaffingWorkerStatus,
)
from cc_crm.services.staffing_deadline_job import pair_deadline
from cc_crm.services.staffing_deadlines import Traffic
from scripts.seed_staffing import seed_staffing

TODAY = date(2026, 10, 11)


def _base(session: Session, candidates: int = 10, clients: int = 3) -> None:
    for index in range(candidates):
        session.add(Candidate(first_name=f"Vorname{index}", last_name=f"Nachname{index}"))
    for index in range(clients):
        session.add(ClientCompany(name=f"Beispielfirma {index}"))
    session.commit()


def test_seed_creates_consistent_dummy_data(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        _base(session)
        result = seed_staffing(session, 8, random.Random(1), TODAY)
        assert (result.workers, result.contracts, result.license_created) == (8, 3, True)
        assert session.scalar(select(func.count()).select_from(StaffingWorker)) == 8
        assert session.scalar(select(func.count()).select_from(StaffingContract)) == 3
        assert session.scalar(select(func.count()).select_from(StaffingLicense)) == 1

        statuses = {a.status for a in session.scalars(select(StaffingAssignment)).all()}
        assert statuses == {
            StaffingAssignmentStatus.ACTIVE,
            StaffingAssignmentStatus.ENDED,
            StaffingAssignmentStatus.PLANNED,
        }
        workers = session.scalars(select(StaffingWorker)).all()
        assert StaffingWorkerStatus.APPLICANT in {w.status for w in workers}
        # Aktive/beendete Einsaetze haben die vollstaendige Checkliste, der geplante nur die Haelfte
        for assignment in session.scalars(select(StaffingAssignment)).all():
            done = session.scalar(
                select(func.count())
                .select_from(StaffingChecklistItem)
                .where(
                    StaffingChecklistItem.assignment_id == assignment.id,
                    StaffingChecklistItem.done.is_(True),
                )
            )
            expected = 3 if assignment.status == StaffingAssignmentStatus.PLANNED else 6
            assert done == expected

        # Die Faelle decken verschiedene Ampelfarben ab (Frist rot/gelb und gruen)
        traffic = {
            pair_deadline(session, a.worker_id, a.client_company_id, TODAY).traffic
            for a in session.scalars(
                select(StaffingAssignment).where(
                    StaffingAssignment.status == StaffingAssignmentStatus.ACTIVE
                )
            ).all()
        }
        assert Traffic.GREEN in traffic
        assert traffic & {Traffic.YELLOW, Traffic.RED}


def test_seed_can_run_twice_and_skips_existing_workers(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _base(session, candidates=6)
        first = seed_staffing(session, 4, random.Random(1), TODAY)
        second = seed_staffing(session, 4, random.Random(2), TODAY)
        assert first.workers == 4
        assert second.workers == 2  # nur noch zwei Kandidaten ohne Profil uebrig
        assert not second.license_created
        assert session.scalar(select(func.count()).select_from(StaffingWorker)) == 6


def test_seed_without_candidates_or_clients_does_nothing(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        assert seed_staffing(session, 5, random.Random(1), TODAY).workers == 0
