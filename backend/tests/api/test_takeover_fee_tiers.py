# ruff: noqa: F811
# NOMICON: Uebernahme-Fee gestaffelt nach Einsatzdauer (einstellbare Tabelle, Platzhalter).
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.errors import BusinessRuleError
from cc_crm.models.candidate import Candidate
from cc_crm.models.staffing import StaffingAssignment, StaffingAssignmentStatus, StaffingWorker
from cc_crm.services.staffing_takeover_fee import (
    DEFAULT_TIERS,
    FeeTier,
    months_between,
    tier_percent,
    validate_tiers,
)
from tests.api.test_staffing_api import Crew, crew, make_candidate  # noqa: F401

P = "/api/v1/staffing"
D = Decimal


def test_months_between_counts_full_calendar_months() -> None:
    assert months_between(date(2026, 1, 15), date(2026, 4, 15)) == 3
    assert months_between(date(2026, 1, 15), date(2026, 4, 14)) == 2
    assert months_between(date(2026, 1, 31), date(2026, 2, 28)) == 0
    assert months_between(date(2025, 11, 10), date(2026, 3, 10)) == 4
    assert months_between(date(2026, 5, 1), date(2026, 4, 1)) == 0  # nie negativ


@pytest.mark.parametrize(
    ("months", "expected"),
    [
        (0, "100"),
        (3, "100"),
        (4, "75"),
        (6, "75"),
        (7, "50"),
        (9, "50"),
        (10, "25"),
        (12, "25"),
        (13, "0"),
        (60, "0"),
    ],
)
def test_default_tiers_are_applied_by_duration(months: int, expected: str) -> None:
    assert tier_percent(months, DEFAULT_TIERS) == D(expected)


def test_tiers_are_validated() -> None:
    validate_tiers(list(DEFAULT_TIERS))
    bad = [
        [],
        [FeeTier(6, D("50"))],  # letzte Stufe darf keine Grenze haben
        [FeeTier(6, D("50")), FeeTier(3, D("20")), FeeTier(None, D("0"))],  # nicht aufsteigend
        [FeeTier(3, D("150")), FeeTier(None, D("0"))],  # ueber 100 %
        [FeeTier(None, D("100")), FeeTier(None, D("0"))],  # Grenze fehlt in der Mitte
    ]
    for tiers in bad:
        with pytest.raises(BusinessRuleError):
            validate_tiers(tiers)


def _active_assignment(session_factory: sessionmaker[Session], crew: Crew, months_ago: int) -> str:
    today = date.today()
    month = today.month - months_ago
    start = date(today.year + (month - 1) // 12, (month - 1) % 12 + 1, 1)
    with session_factory() as session:
        candidate = Candidate(first_name="Tina", last_name="Staffel")
        session.add(candidate)
        session.flush()
        worker = StaffingWorker(candidate_id=candidate.id)
        session.add(worker)
        session.flush()
        row = StaffingAssignment(
            worker_id=worker.id,
            client_company_id=uuid.UUID(crew.client_id),
            owner_user_id=uuid.UUID(crew.a.id),
            start_date=start,
            status=StaffingAssignmentStatus.ACTIVE,
        )
        session.add(row)
        session.commit()
        return str(row.id)


def test_tiers_are_admin_editable_and_listed(client: TestClient, crew: Crew) -> None:
    listed = client.get(f"{P}/takeover-fee-tiers", headers=crew.b.headers).json()  # Teamleiter
    assert [t["up_to_months"] for t in listed["tiers"]] == [3, 6, 9, 12, None]
    assert "Platzhalter" in listed["notice"]
    body = {
        "tiers": [
            {"up_to_months": 6, "percent_of_fee": "50"},
            {"up_to_months": None, "percent_of_fee": "10"},
        ]
    }
    assert (
        client.put(f"{P}/takeover-fee-tiers", json=body, headers=crew.b.headers).status_code == 403
    )
    saved = client.put(f"{P}/takeover-fee-tiers", json=body, headers=crew.admin.headers)
    assert saved.status_code == 200, saved.text
    assert [Decimal(t["percent_of_fee"]) for t in saved.json()["tiers"]] == [D("50"), D("10")]
    invalid = {"tiers": [{"up_to_months": 6, "percent_of_fee": "50"}]}
    assert (
        client.put(f"{P}/takeover-fee-tiers", json=invalid, headers=crew.admin.headers).status_code
        == 422
    )
    assert (
        "staffing_takeover_fee_tiers"
        in client.get("/api/v1/audit-logs", headers=crew.admin.headers).text
    )


def test_takeover_fee_follows_the_duration_tier(
    client: TestClient, crew: Crew, session_factory: sessionmaker[Session]
) -> None:
    assignment_id = _active_assignment(session_factory, crew, months_ago=5)  # 5 Monate -> 75 %
    preview = client.get(
        f"{P}/assignments/{assignment_id}/takeover-preview", headers=crew.a.headers
    ).json()
    assert preview["months_worked"] == 5
    assert D(preview["tier_percent"]) == D("75")
    assert D(preview["base_fee_percentage"]) == D("27")  # Honorarsatz des Kunden
    assert D(preview["effective_fee_percentage"]) == D("20.25")  # 27 x 75 %
    # Fremder Disponent: wie bei jeder Einsatz-Route 404
    assert (
        client.get(
            f"{P}/assignments/{assignment_id}/takeover-preview", headers=crew.c.headers
        ).status_code
        == 404
    )
    done = client.post(
        f"{P}/assignments/{assignment_id}/takeover",
        json={"annual_salary": "50000"},
        headers=crew.a.headers,
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["months_worked"] == 5 and D(body["tier_percent"]) == D("75")
    submission = client.get(
        f"/api/v1/submissions/{body['submission_id']}", headers=crew.a.headers
    ).json()
    assert submission["fee_percentage"] == "20.25"
    assert submission["expected_fee"] == "10125.00"  # 50.000 x 20,25 %


def test_an_explicit_percentage_overrides_the_tier(
    client: TestClient, crew: Crew, session_factory: sessionmaker[Session]
) -> None:
    assignment_id = _active_assignment(session_factory, crew, months_ago=20)  # sonst 0 %
    done = client.post(
        f"{P}/assignments/{assignment_id}/takeover",
        json={"annual_salary": "60000", "fee_percentage": "25"},
        headers=crew.a.headers,
    )
    assert done.status_code == 200, done.text
    assert done.json()["tier_percent"] is None
    assert D(done.json()["applied_fee_percentage"]) == D("25")
