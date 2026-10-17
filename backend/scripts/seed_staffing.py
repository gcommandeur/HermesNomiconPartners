# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Dummy-Daten für die Überlassung (Leiharbeitnehmer, Verträge, Einsätze, Erlaubnis).

Wird von `seed_data.py seed --staffing N` aufgerufen und arbeitet auf den dort angelegten
Kandidaten und Kanzleien. NUR für lokale Entwicklungsdatenbanken (Dummy-Daten, nie Produktion):
alle Personen, Nummern und Aktenzeichen sind erfunden.

Die Daten gehen durch die echten Services (Regeln, Checkliste, Audit-Log wie im Betrieb) und
decken verschiedene Faelle ab: Frist rot/gelb/gruen, Lücke unter 3 Monaten (Zähler läuft
weiter), beendeter und geplanter Einsatz, Anwärter ohne Einsatz."""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.core.security import hash_password  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.engagement import CandidateEngagementPrefs  # noqa: E402
from cc_crm.models.enums import ClientStatus  # noqa: E402
from cc_crm.models.staffing import (  # noqa: E402
    StaffingAssignmentStatus,
    StaffingChecklistKey,
    StaffingLicense,
    StaffingWorker,
    StaffingWorkerStatus,
)
from cc_crm.models.user import User  # noqa: E402
from cc_crm.schemas.staffing import (  # noqa: E402
    StaffingAssignmentCreate,
    StaffingAssignmentStatusChange,
    StaffingChecklistItemUpdate,
    StaffingContractCreate,
    StaffingLicenseCreate,
    StaffingWorkerCreate,
)
from cc_crm.services.staffing_activation import StaffingActivationService  # noqa: E402
from cc_crm.services.staffing_assignments import (  # noqa: E402
    StaffingAssignmentService,
    StaffingContractService,
)
from cc_crm.services.staffing_licenses import StaffingLicenseService  # noqa: E402
from cc_crm.services.staffing_workers import StaffingWorkerService  # noqa: E402

PAY_GRADES = ["EG 1", "EG 2", "EG 3", "EG 4"]
ACTIVITIES = ["Kommissionierung", "Staplerfahrer", "Montage", "Maschinenbedienung", "Lagerhilfe"]
LOCATIONS = ["Halle 1", "Lager Nord", "Werk Sued", "Versand"]


@dataclass
class StaffingSeedResult:
    workers: int = 0
    contracts: int = 0
    assignments: int = 0
    license_created: bool = False


@dataclass
class _Plan:
    """Ein Einsatz: Tage vor heute bei Beginn (negativ = Zukunft), Status, Tage vor Ende."""

    start_days_ago: int
    status: StaffingAssignmentStatus
    end_days_ago: int | None = None


# Reihenfolge = Reihenfolge der Leiharbeitnehmer; ab dem 9. wird von vorn begonnen.
SCENARIOS: list[list[_Plan]] = [
    [_Plan(520, StaffingAssignmentStatus.ACTIVE)],  # ~17 Monate -> Frist rot/gelb
    [_Plan(120, StaffingAssignmentStatus.ACTIVE)],  # gruen
    [_Plan(300, StaffingAssignmentStatus.ACTIVE)],  # Equal Pay läuft schon
    [  # Lücke von 50 Tagen: Zähler läuft weiter
        _Plan(400, StaffingAssignmentStatus.ENDED, 200),
        _Plan(150, StaffingAssignmentStatus.ACTIVE),
    ],
    [_Plan(-20, StaffingAssignmentStatus.PLANNED)],  # beginnt in 20 Tagen, Checkliste halb
    [],  # Anwärter ohne Einsatz
    [_Plan(200, StaffingAssignmentStatus.ENDED, 60)],  # beendet
    [_Plan(30, StaffingAssignmentStatus.ACTIVE)],
]


def _seed_actor(session: Session) -> User:
    user = session.scalar(select(User).order_by(User.created_at))
    if user is not None:
        return user
    user = User(email="seed-script@cc-crm.local", hashed_password=hash_password("not-a-real-login"))
    session.add(user)
    session.flush()
    return user


def _ensure_license(session: Session, actor: User, today: date) -> bool:
    if session.scalar(select(StaffingLicense.id).limit(1)) is not None:
        return False
    StaffingLicenseService(session).create(
        StaffingLicenseCreate(
            authority="Bundesagentur für Arbeit (Beispiel)",
            file_number="DEMO-AÜG-0001",
            valid_from=today - timedelta(days=900),
            valid_to=today + timedelta(days=500),
        ),
        actor,
    )
    return True


def seed_staffing(
    session: Session,
    workers: int,
    rng: random.Random | None = None,
    today: date | None = None,
) -> StaffingSeedResult:
    """Legt bis zu `workers` Leiharbeitnehmer aus vorhandenen Kandidaten an (Kandidaten, die
    schon Leiharbeitnehmer sind, werden übersprungen). Mehrfaches Ausführen ist möglich."""
    rand = rng or random.Random()
    day = today or date.today()
    result = StaffingSeedResult()
    actor = _seed_actor(session)
    result.license_created = _ensure_license(session, actor, day)

    taken = select(StaffingWorker.candidate_id)
    candidates = session.scalars(
        select(Candidate)
        .where(Candidate.id.not_in(taken), Candidate.anonymized_at.is_(None))
        .order_by(Candidate.created_at)
        .limit(workers)
    ).all()
    clients = session.scalars(
        select(ClientCompany).where(ClientCompany.status != ClientStatus.BLOCKED).limit(3)
    ).all()
    if not candidates or not clients:
        return result

    contracts = {}
    for index, client in enumerate(clients):
        contract = StaffingContractService(session).create(
            StaffingContractCreate(
                client_company_id=client.id,
                contract_number=f"R-DEMO-{day.year}-{index + 1:02d}",
                valid_from=day - timedelta(days=700),
                industry_sector=rand.choice(["Logistik", "Metall", "Handel"]),
                status="active",
            ),
            actor,
        )
        contracts[client.id] = contract.contract.id
        result.contracts += 1

    worker_service = StaffingWorkerService(session)
    assignment_service = StaffingAssignmentService(session)
    activation = StaffingActivationService(session)
    for index, candidate in enumerate(candidates):
        plans = SCENARIOS[index % len(SCENARIOS)]
        session.add(CandidateEngagementPrefs(candidate_id=candidate.id, open_for_staffing="yes"))
        session.flush()
        worker = worker_service.create(
            StaffingWorkerCreate(
                candidate_id=candidate.id,
                # Statusregel: Aktiv erst ab begonnenem Einsatz; geplante Einsätze -> Anwärter
                status=(
                    StaffingWorkerStatus.ACTIVE
                    if plans and plans[0].status != StaffingAssignmentStatus.PLANNED
                    else StaffingWorkerStatus.APPLICANT
                ),
                entry_date=(
                    day - timedelta(days=plans[0].start_days_ago)
                    if plans and plans[0].status != StaffingAssignmentStatus.PLANNED
                    else None
                ),
                hourly_wage=Decimal(rand.choice(["13.80", "14.50", "15.20", "16.75", "18.10"])),
                pay_grade=rand.choice(PAY_GRADES),
                weekly_hours=Decimal(rand.choice(["35", "38.5", "40"])),
            ),
            actor,
        ).worker
        result.workers += 1
        client = clients[index % len(clients)]
        for plan in plans:
            start = day - timedelta(days=plan.start_days_ago)
            end = None if plan.end_days_ago is None else day - timedelta(days=plan.end_days_ago)
            row = assignment_service.create(
                StaffingAssignmentCreate(
                    worker_id=worker.id,
                    client_company_id=client.id,
                    contract_id=contracts[client.id],
                    start_date=start,
                    location=rand.choice(LOCATIONS),
                    activity=rand.choice(ACTIVITIES),
                    billing_rate=Decimal(rand.choice(["27.50", "29.00", "31.40", "34.00"])),
                ),
                actor,
            )
            result.assignments += 1
            assignment_id = row.assignment.id
            # "Überlassungsvertrag" ergibt sich aus dem verknüpften Vertrag und ist nicht abhakbar
            items = [
                item
                for item in assignment_service.detail(assignment_id, day).checklist
                if item.item_key != StaffingChecklistKey.SUPPLY_CONTRACT
            ]
            done_count = (
                len(items) // 2 if plan.status == StaffingAssignmentStatus.PLANNED else len(items)
            )
            for item in items[:done_count]:
                assignment_service.update_checklist_item(
                    assignment_id, item.id, StaffingChecklistItemUpdate(done=True), actor
                )
            if plan.status == StaffingAssignmentStatus.PLANNED:
                continue
            # Aktivierung nach den echten Regeln; rueckdatiert wie bei einem Altbestand.
            activation.change_status(
                assignment_id,
                StaffingAssignmentStatusChange(status=StaffingAssignmentStatus.ACTIVE),
                actor,
                today=start,
            )
            if plan.status == StaffingAssignmentStatus.ENDED:
                activation.change_status(
                    assignment_id,
                    StaffingAssignmentStatusChange(
                        status=StaffingAssignmentStatus.ENDED, actual_end_date=end
                    ),
                    actor,
                    today=end or day,
                )
    return result
