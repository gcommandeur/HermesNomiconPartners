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


# --- Sonderfaelle der Logikluecken-Pakete ----------------------------------------------------


def _worker_of(session: Session, key: str) -> StaffingWorker:
    return session.scalars(
        select(StaffingWorker).where(StaffingWorker.notes == f"Demo-Fall: {key}")
    ).one()


def _assignments_of(session: Session, worker: StaffingWorker) -> list[StaffingAssignment]:
    return list(
        session.scalars(
            select(StaffingAssignment)
            .where(StaffingAssignment.worker_id == worker.id)
            .order_by(StaffingAssignment.start_date)
        )
    )


def test_seed_edge_cases_cover_the_new_logic_and_run_only_once(
    session_factory: sessionmaker[Session],
) -> None:
    from datetime import timedelta

    from cc_crm.models.enums import TaskStatus
    from cc_crm.models.recruiting import AuditLog
    from cc_crm.models.staffing import StaffingPriorPeriod
    from cc_crm.models.task import Task
    from cc_crm.services.staffing_assignments import is_overdue
    from cc_crm.services.staffing_equal_pay import pair_equal_pay_confirmed_on

    day = date.today()  # die Dienste rechnen teils mit dem echten "heute"
    with session_factory() as session:
        _base(session, candidates=16)
        first = seed_staffing(session, 4, random.Random(1), day, edge_cases=True)
        assert first.edge_cases == 8
        marked = session.scalars(
            select(StaffingWorker).where(StaffingWorker.notes.like("Demo-Fall:%"))
        ).all()
        assert len(marked) == 8

        # Vorzeit: 10 Monate beim Kunden zaehlen mit, Equal Pay deshalb schon erreicht
        worker = _worker_of(session, "vorzeit")
        prior = session.scalars(
            select(StaffingPriorPeriod).where(StaffingPriorPeriod.worker_id == worker.id)
        ).one()
        deadline = pair_deadline(session, worker.id, prior.client_company_id, day)
        assert deadline.prior_days == 305 and deadline.equal_pay_reached

        # "Keine Vorzeiten" bestaetigt: Frist nicht vorlaeufig; ohne Bestaetigung vorlaeufig
        worker = _worker_of(session, "keine_vorzeiten")
        (confirmed_assignment,) = _assignments_of(session, worker)
        assert not pair_deadline(
            session, worker.id, confirmed_assignment.client_company_id, day
        ).provisional
        unconfirmed = _worker_of(session, "ueberfaellig")
        (open_one,) = _assignments_of(session, unconfirmed)
        assert (
            "prior_unconfirmed"
            in pair_deadline(
                session, unconfirmed.id, open_one.client_company_id, day
            ).provisional_reasons
        )

        # ueberfaelliger aktiver Einsatz
        worker = _worker_of(session, "ueberfaellig")
        (overdue,) = _assignments_of(session, worker)
        assert overdue.status == StaffingAssignmentStatus.ACTIVE and is_overdue(overdue, day)

        # bestaetigte Ueberschneidung: ein aktiver und ein geplanter Einsatz, Audit-Eintrag
        worker = _worker_of(session, "ueberschneidung")
        active, planned = _assignments_of(session, worker)
        assert (active.status, planned.status) == (
            StaffingAssignmentStatus.ACTIVE,
            StaffingAssignmentStatus.PLANNED,
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.entity_id == planned.id, AuditLog.action == "overlap_acknowledged")
            )
            == 1
        )

        # Equal Pay: kurz davor / offen / bestaetigt
        near = _worker_of(session, "equal_pay_nah")
        (near_assignment,) = _assignments_of(session, near)
        near_deadline = pair_deadline(session, near.id, near_assignment.client_company_id, day)
        assert not near_deadline.equal_pay_reached
        assert near_deadline.equal_pay_from is not None
        assert 0 < (near_deadline.equal_pay_from - day).days <= 30
        for key, confirmed in (("equal_pay_offen", False), ("equal_pay_bestaetigt", True)):
            person = _worker_of(session, key)
            (assignment,) = _assignments_of(session, person)
            result = pair_deadline(session, person.id, assignment.client_company_id, day)
            assert result.equal_pay_reached
            on = pair_equal_pay_confirmed_on(
                session, person.id, assignment.client_company_id, result.chain_start
            )
            assert (on is not None) is confirmed

        # Vertrag, der den Zeitraum nicht mehr deckt: aktiver Einsatz + Aufgabe (nicht gesperrt)
        worker = _worker_of(session, "vertrag_luecke")
        (gap,) = _assignments_of(session, worker)
        contract = session.get(StaffingContract, gap.contract_id)
        assert gap.status == StaffingAssignmentStatus.ACTIVE
        assert contract is not None and contract.valid_to == day - timedelta(days=3)
        gap_tasks = session.scalars(
            select(Task).where(Task.title.startswith("Überlassungsvertrag deckt"))
        ).all()
        assert len(gap_tasks) == 1 and gap_tasks[0].status == TaskStatus.OPEN

        # Idempotent: ein zweiter Lauf legt keinen Sonderfall doppelt an
        second = seed_staffing(session, 2, random.Random(2), day, edge_cases=True)
        assert second.edge_cases == 0
        assert (
            len(
                session.scalars(
                    select(StaffingWorker).where(StaffingWorker.notes.like("Demo-Fall:%"))
                ).all()
            )
            == 8
        )
