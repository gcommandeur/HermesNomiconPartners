"""Die SQL-Aggregation des Cockpits (services/operational.py::CockpitService) muss
fuer dieselben Daten dasselbe Ergebnis liefern wie die frueheren Python-Schleifen
(tests/legacy_cockpit.py, eingefroren). Zufaellige, aber reproduzierbare Datenbestaende
(feste Seeds) mit allen relevanten Sonderfaellen: archivierte/stornierte Prozesse,
Angebote ohne Prozess-Eintrag, Rechnungen in jedem Status, zurueckgestellte und
nicht faellige Aufgaben, Eigentuemer-Filter, geteilte Prozesse."""

import random
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.activity import Activity
from cc_crm.models.candidate import Candidate
from cc_crm.models.candidate_pitch_log import CandidatePitchLog
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import (
    InvoiceStatus,
    SubmissionStatus,
    TaskPriority,
    TaskStatus,
)
from cc_crm.models.operational import SourcingMetric
from cc_crm.models.recruiting import AuditLog, Fee, Offer, Placement
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.task import Task
from cc_crm.models.user import User
from cc_crm.services.operational import CockpitService
from tests.legacy_cockpit import LegacyCockpitService


def _days(rng: random.Random, low: int, high: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=rng.uniform(low, high))


def _seed(session: Session, seed: int) -> dict[str, list[uuid.UUID]]:
    rng = random.Random(seed)
    users = [
        User(email=f"u{i}@example.com", hashed_password=hash_password("x")) for i in range(3)
    ]
    session.add_all(users)
    companies = [ClientCompany(name=f"Kanzlei {i}") for i in range(6)]
    session.add_all(companies)
    session.flush()
    candidates = []
    for i in range(60):
        candidates.append(
            Candidate(
                first_name=f"Vorname{i}",
                last_name=f"Nachname{i}",
                owner_user_id=rng.choice([*(u.id for u in users), None]),
                cv_in_recorded_at=_days(rng, 0, 200) if rng.random() < 0.5 else None,
            )
        )
    session.add_all(candidates)
    session.flush()

    statuses = list(SubmissionStatus)
    submissions = []
    for _i in range(90):
        status = rng.choice(statuses)
        created = _days(rng, 0, 150)
        submissions.append(
            CandidateSubmission(
                candidate_id=rng.choice(candidates).id,
                client_company_id=rng.choice([*(c.id for c in companies), None]),
                owner_user_id=rng.choice([*(u.id for u in users), None]),
                status=status,
                expected_fee=Decimal(rng.randint(0, 30000)) if rng.random() < 0.7 else None,
                next_step=rng.choice([None, "Rueckruf", "Angebot besprechen"]),
                follow_up_at=_days(rng, -5, 10) if rng.random() < 0.5 else None,
                archived_at=_days(rng, 0, 20) if rng.random() < 0.15 else None,
                created_at=created,
            )
        )
    session.add_all(submissions)
    session.flush()

    for sub in submissions:
        if rng.random() < 0.4:
            session.add(
                Offer(
                    submission_id=sub.id,
                    offered_salary=Decimal(rng.randint(40000, 90000)),
                    created_at=_days(rng, 0, 120),
                )
            )
    placements = []
    for sub in submissions:
        if rng.random() < 0.3:
            placement = Placement(
                submission_id=sub.id,
                start_date=date.today() - timedelta(days=rng.randint(0, 100)),
                final_salary=Decimal(rng.randint(40000, 90000)),
                fee_percentage=Decimal("25.00"),
                calculated_fee=Decimal(rng.randint(5000, 25000)),
                created_at=_days(rng, 0, 120),
            )
            placements.append(placement)
    session.add_all(placements)
    session.flush()
    for placement in placements:
        for _ in range(rng.randint(0, 3)):
            net = Decimal(rng.randint(1000, 9000))
            session.add(
                Fee(
                    placement_id=placement.id,
                    amount_net=net,
                    vat_rate=Decimal("19.00"),
                    amount_gross=net * Decimal("1.19"),
                    invoice_status=rng.choice(list(InvoiceStatus)),
                    created_at=_days(rng, 0, 130),
                )
            )

    for _ in range(70):
        sub = rng.choice(submissions)
        session.add(
            AuditLog(
                entity_type="candidate_submission",
                entity_id=sub.id,
                action="status_changed",
                changed_at=_days(rng, 0, 120),
                new_values={"status": rng.choice(statuses).value},
            )
        )
    for _ in range(25):
        sub = rng.choice(submissions)
        session.add(
            Activity(
                candidate_id=sub.candidate_id,
                candidate_submission_id=sub.id,
                activity_type="submission_status_changed",
                subject="Statuswechsel",
                details=rng.choice(["cv_out -> interview", "interview -> offer", "x -> cancelled"]),
                occurred_at=_days(rng, 0, 100),
            )
        )
    for _ in range(40):
        session.add(
            CandidatePitchLog(
                candidate_id=rng.choice(candidates).id, occurred_at=_days(rng, 0, 120)
            )
        )
    session.add(
        SourcingMetric(
            period_start=date.today() - timedelta(days=5),
            period_end=date.today() - timedelta(days=1),
            pitches=5,
            responses=2,
            positive_responses=1,
            qualification_calls=1,
        )
    )

    for _ in range(50):
        sub = rng.choice([None, *submissions])
        cand = rng.choice([None, *candidates])
        session.add(
            Task(
                title=f"Aufgabe {rng.randint(0, 999)}",
                owner_user_id=rng.choice([*(u.id for u in users), None]),
                candidate_id=cand.id if cand and rng.random() < 0.6 else None,
                candidate_submission_id=sub.id if sub and rng.random() < 0.6 else None,
                status=rng.choice(
                    [TaskStatus.OPEN, TaskStatus.OPEN, TaskStatus.IN_PROGRESS, TaskStatus.DONE]
                ),
                priority=rng.choice(list(TaskPriority)),
                due_at=_days(rng, -4, 6) if rng.random() < 0.8 else None,
                snoozed_until=(
                    datetime.now(UTC) + timedelta(days=rng.uniform(-2, 3))
                    if rng.random() < 0.3
                    else None
                ),
            )
        )
    session.commit()
    return {
        "users": [u.id for u in users],
        "shared": [s.id for s in rng.sample(submissions, 5)],
    }


def _normalize(value: object) -> object:
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        items = [_normalize(item) for item in value]
        return sorted(
            items,
            key=lambda item: repr(sorted(item.items())) if isinstance(item, dict) else repr(item),
        )
    if isinstance(value, float):
        return pytest.approx(value, abs=0.051)  # Rundung auf 1-2 Stellen
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("period", ["week", "month", "quarter"])
def test_new_cockpit_equals_the_legacy_calculation(
    session_factory: sessionmaker[Session], seed: int, period: str
) -> None:
    with session_factory() as session:
        refs = _seed(session, seed)
        u0, u1, u2 = refs["users"]
        filters: list[tuple[list[uuid.UUID] | None, list[uuid.UUID]]] = [
            (None, []),
            ([u0], []),
            ([u0, u1], []),
            ([u2], refs["shared"]),
            ([], []),
        ]
        for owner_ids, shared in filters:
            expected = LegacyCockpitService(session).build(
                period, owner_user_ids=owner_ids, shared_submission_ids=shared
            )
            actual = CockpitService(session).build(
                period, owner_user_ids=owner_ids, shared_submission_ids=shared
            )
            assert _normalize(actual) == _normalize(expected), (
                f"seed={seed} period={period} owners={owner_ids} shared={bool(shared)}"
            )


def test_the_comparison_is_not_vacuous(session_factory: sessionmaker[Session]) -> None:
    """Die Testdaten muessen in jedem Bereich des Ergebnisses etwas erzeugen."""
    with session_factory() as session:
        _seed(session, 1)
        result = CockpitService(session).build("quarter", owner_user_ids=None)
    assert result["important"] and result["hot_processes"]
    kpis = result["kpis"]
    assert kpis["submissions"] > 0 and kpis["offers"] > 0 and kpis["placements"] > 0
    assert kpis["pitches"] > 0 and kpis["expected_fees"] > 0 and kpis["cv_available"] > 0
    assert kpis["interviews"] > 0
    assert result["recruiting_kpis"]["time_to_fill_days"] is not None
    assert result["recruiting_kpis"]["average_fee_per_placement"] is not None
