# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Datenmodell und Services der Ueberlassung: Leiharbeitnehmer, Vertraege, Einsaetze, Erlaubnis."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.errors import BusinessRuleError, ConflictError, EntityNotFoundError
from cc_crm.core.security import hash_password
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.engagement import CandidateEngagementPrefs
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.staffing import (
    CHECKLIST_KEYS,
    StaffingChecklistKey,
    StaffingContractStatus,
    StaffingWorkerStatus,
)
from cc_crm.models.user import User
from cc_crm.schemas.staffing import (
    StaffingAssignmentCreate,
    StaffingAssignmentUpdate,
    StaffingChecklistItemUpdate,
    StaffingContractCreate,
    StaffingLicenseCreate,
    StaffingWorkerCreate,
    StaffingWorkerUpdate,
)
from cc_crm.services.staffing_assignments import (
    StaffingAssignmentService,
    StaffingContractService,
)
from cc_crm.services.staffing_licenses import StaffingLicenseService
from cc_crm.services.staffing_workers import StaffingWorkerService


@pytest.fixture
def session(session_factory: sessionmaker[Session]):  # type: ignore[no-untyped-def]
    with session_factory() as s:
        yield s


@pytest.fixture
def actor(session: Session) -> User:
    user = User(email="dispo@nomicon.example", hashed_password=hash_password("x"))
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def candidate(session: Session) -> Candidate:
    c = Candidate(first_name="Mira", last_name="Muster")
    session.add(c)
    session.flush()
    session.add(CandidateEngagementPrefs(candidate_id=c.id, open_for_staffing="yes"))
    session.commit()
    return c


@pytest.fixture
def client_company(session: Session) -> ClientCompany:
    c = ClientCompany(name="Beispiel Logistik GmbH")
    session.add(c)
    session.commit()
    return c


def test_worker_is_one_to_one_with_candidate(
    session: Session, actor: User, candidate: Candidate
) -> None:
    service = StaffingWorkerService(session)
    row = service.create(
        StaffingWorkerCreate(candidate_id=candidate.id, hourly_wage=Decimal("14.50")), actor
    )
    assert row.candidate_name == "Mira Muster"
    assert row.worker.status == StaffingWorkerStatus.APPLICANT
    with pytest.raises(ConflictError):
        service.create(StaffingWorkerCreate(candidate_id=candidate.id), actor)
    assert service.row_for_candidate(candidate.id) is not None


def test_worker_rejects_unknown_and_anonymized_candidates(session: Session, actor: User) -> None:
    import uuid
    from datetime import UTC, datetime

    service = StaffingWorkerService(session)
    with pytest.raises(EntityNotFoundError):
        service.create(StaffingWorkerCreate(candidate_id=uuid.uuid4()), actor)
    anonymous = Candidate(first_name="Anonymisiert", last_name="Anonymisiert")
    anonymous.anonymized_at = datetime.now(UTC)
    session.add(anonymous)
    session.commit()
    with pytest.raises(BusinessRuleError):
        service.create(StaffingWorkerCreate(candidate_id=anonymous.id), actor)


def test_worker_update_writes_audit_only_for_real_changes(
    session: Session, actor: User, candidate: Candidate
) -> None:
    service = StaffingWorkerService(session)
    worker = service.create(
        StaffingWorkerCreate(candidate_id=candidate.id, hourly_wage=Decimal("14.50")), actor
    ).worker
    service.update(worker.id, StaffingWorkerUpdate(hourly_wage=Decimal("14.50")), actor)
    service.update(worker.id, StaffingWorkerUpdate(hourly_wage=Decimal("15.00")), actor)
    entries = session.scalars(
        select(AuditLog).where(AuditLog.entity_id == worker.id).order_by(AuditLog.changed_at)
    ).all()
    assert [e.action for e in entries] == ["created", "updated"]
    assert entries[1].new_values == {"hourly_wage": "15.00"}
    assert entries[1].changed_by == actor.email


def test_worker_update_validates_dates(session: Session, actor: User, candidate: Candidate) -> None:
    service = StaffingWorkerService(session)
    worker = service.create(
        StaffingWorkerCreate(candidate_id=candidate.id, entry_date=date(2026, 5, 1)), actor
    ).worker
    with pytest.raises(BusinessRuleError):
        service.update(worker.id, StaffingWorkerUpdate(exit_date=date(2026, 4, 1)), actor)


def test_assignment_gets_full_checklist_and_default_wage(
    session: Session, actor: User, candidate: Candidate, client_company: ClientCompany
) -> None:
    worker = (
        StaffingWorkerService(session)
        .create(
            StaffingWorkerCreate(
                candidate_id=candidate.id,
                status=StaffingWorkerStatus.ACTIVE,
                hourly_wage=Decimal("14.50"),
            ),
            actor,
        )
        .worker
    )
    service = StaffingAssignmentService(session)
    row = service.create(
        StaffingAssignmentCreate(
            worker_id=worker.id,
            client_company_id=client_company.id,
            start_date=date(2026, 6, 1),
            billing_rate=Decimal("28.00"),
        ),
        actor,
    )
    assignment = row.assignment
    assert assignment.owner_user_id == actor.id  # Standard: der anlegende Nutzer
    assert assignment.hourly_wage == Decimal("14.50")  # aus dem Leiharbeitnehmer uebernommen
    assert (row.checklist_done, row.checklist_total) == (0, len(CHECKLIST_KEYS))
    detail = service.detail(assignment.id)
    assert [item.item_key for item in detail.checklist] == list(CHECKLIST_KEYS)
    assert not service.checklist_complete(assignment.id)

    for item in detail.checklist:
        if item.item_key == StaffingChecklistKey.SUPPLY_CONTRACT:
            # ergibt sich aus dem verknuepften Vertrag, nicht von Hand abhakbar
            with pytest.raises(BusinessRuleError, match="automatisch"):
                service.update_checklist_item(
                    assignment.id, item.id, StaffingChecklistItemUpdate(done=True), actor
                )
            continue
        service.update_checklist_item(
            assignment.id, item.id, StaffingChecklistItemUpdate(done=True), actor
        )
    assert not service.checklist_complete(assignment.id)
    contract = StaffingContractService(session).create(
        StaffingContractCreate(
            client_company_id=client_company.id,
            valid_from=date(2026, 1, 1),
            status=StaffingContractStatus.ACTIVE,
        ),
        actor,
    )
    service.update(assignment.id, StaffingAssignmentUpdate(contract_id=contract.contract.id), actor)
    assert service.checklist_complete(assignment.id)
    assert service.get_row(assignment.id).checklist_done == len(CHECKLIST_KEYS)


def test_assignment_refused_for_left_worker_and_foreign_contract(
    session: Session, actor: User, candidate: Candidate, client_company: ClientCompany
) -> None:
    worker = (
        StaffingWorkerService(session)
        .create(
            StaffingWorkerCreate(candidate_id=candidate.id, status=StaffingWorkerStatus.LEFT), actor
        )
        .worker
    )
    service = StaffingAssignmentService(session)
    with pytest.raises(BusinessRuleError):
        service.create(
            StaffingAssignmentCreate(
                worker_id=worker.id,
                client_company_id=client_company.id,
                start_date=date(2026, 6, 1),
            ),
            actor,
        )

    StaffingWorkerService(session).update(
        worker.id, StaffingWorkerUpdate(status=StaffingWorkerStatus.ACTIVE), actor
    )
    other_client = ClientCompany(name="Andere Firma GmbH")
    session.add(other_client)
    session.commit()
    contract = StaffingContractService(session).create(
        StaffingContractCreate(client_company_id=other_client.id, contract_number="R-1"), actor
    )
    with pytest.raises(BusinessRuleError):
        service.create(
            StaffingAssignmentCreate(
                worker_id=worker.id,
                client_company_id=client_company.id,
                contract_id=contract.contract.id,
                start_date=date(2026, 6, 1),
            ),
            actor,
        )


def test_assignment_update_blocked_after_end(
    session: Session, actor: User, candidate: Candidate, client_company: ClientCompany
) -> None:
    worker = (
        StaffingWorkerService(session)
        .create(
            StaffingWorkerCreate(candidate_id=candidate.id, status=StaffingWorkerStatus.ACTIVE),
            actor,
        )
        .worker
    )
    service = StaffingAssignmentService(session)
    row = service.create(
        StaffingAssignmentCreate(
            worker_id=worker.id, client_company_id=client_company.id, start_date=date(2026, 6, 1)
        ),
        actor,
    )
    with pytest.raises(BusinessRuleError):
        service.update(
            row.assignment.id, StaffingAssignmentUpdate(planned_end_date=date(2026, 5, 1)), actor
        )
    from cc_crm.models.staffing import StaffingAssignmentStatus

    row.assignment.status = StaffingAssignmentStatus.ENDED
    session.commit()
    with pytest.raises(BusinessRuleError):
        service.update(row.assignment.id, StaffingAssignmentUpdate(location="Halle 3"), actor)


def test_license_covering_period(session: Session, actor: User) -> None:
    service = StaffingLicenseService(session)
    service.create(
        StaffingLicenseCreate(
            authority="Bundesagentur fuer Arbeit",
            valid_from=date(2025, 1, 1),
            valid_to=date(2026, 12, 31),
        ),
        actor,
    )
    assert service.licenses.covering(date(2026, 1, 1), date(2026, 12, 31)) is not None
    assert service.licenses.covering(date(2026, 1, 1), date(2027, 1, 1)) is None
    assert service.licenses.covering(date(2024, 12, 31), None) is None
    assert service.licenses.covering(date(2026, 1, 1), None) is None  # offenes Ende, befristet
    service.create(
        StaffingLicenseCreate(authority="BA", valid_from=date(2026, 6, 1), valid_to=None), actor
    )
    assert service.licenses.covering(date(2026, 7, 1), None) is not None


def test_candidate_history_never_contains_staffing_entries(
    session: Session, actor: User, candidate: Candidate
) -> None:
    from cc_crm.repositories.recruiting import AuditLogRepository

    StaffingWorkerService(session).create(
        StaffingWorkerCreate(candidate_id=candidate.id, hourly_wage=Decimal("14.50")), actor
    )
    history = AuditLogRepository(session).list_for_candidate(candidate.id, [])
    assert list(history) == []


def test_status_rule_active_never_in_the_future(
    session: Session, actor: User, candidate: Candidate
) -> None:
    """Statusregel: Aktiv erst ab Eintritt/Einsatzbeginn, vorher bleibt die Person "In Auswahl"."""
    from datetime import timedelta

    service = StaffingWorkerService(session)
    future = date.today() + timedelta(days=20)
    with pytest.raises(BusinessRuleError, match="In Auswahl"):
        service.create(
            StaffingWorkerCreate(
                candidate_id=candidate.id,
                status=StaffingWorkerStatus.ACTIVE,
                entry_date=future,
            ),
            actor,
        )
    # "In Auswahl" mit künftigem Eintritt ist erlaubt ...
    row = service.create(StaffingWorkerCreate(candidate_id=candidate.id, entry_date=future), actor)
    assert row.worker.status == StaffingWorkerStatus.APPLICANT
    # ... aber nicht als "aktiv" umstellbar, solange der Eintritt in der Zukunft liegt
    with pytest.raises(BusinessRuleError, match="In Auswahl"):
        service.update(
            row.worker.id, StaffingWorkerUpdate(status=StaffingWorkerStatus.ACTIVE), actor
        )
    past = date.today() - timedelta(days=5)
    updated = service.update(
        row.worker.id,
        StaffingWorkerUpdate(status=StaffingWorkerStatus.ACTIVE, entry_date=past),
        actor,
    )
    assert updated.worker.status == StaffingWorkerStatus.ACTIVE


def test_assignment_cannot_be_activated_before_its_start(
    session: Session, actor: User, candidate: Candidate, client_company: ClientCompany
) -> None:
    from datetime import timedelta

    from cc_crm.services.staffing_activation import StaffingActivationService

    worker = StaffingWorkerService(session).create(
        StaffingWorkerCreate(candidate_id=candidate.id), actor
    ).worker
    start = date.today() + timedelta(days=10)
    row = StaffingAssignmentService(session).create(
        StaffingAssignmentCreate(
            worker_id=worker.id, client_company_id=client_company.id, start_date=start
        ),
        actor,
    )
    problems = StaffingActivationService(session).activation_problems(
        row.assignment.id, date.today()
    )
    assert any("beginnt erst am" in problem for problem in problems)
    assert not any(
        "beginnt erst am" in problem
        for problem in StaffingActivationService(session).activation_problems(
            row.assignment.id, start
        )
    )
