# ruff: noqa: F811
# NOMICON: Bruecken Direct und Ueberlassung: "Als Einsatz anbieten", Geschaeft mit einer Kanzlei.
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.access_views import UserViewAccess
from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import InvoiceStatus, SubmissionStatus
from cc_crm.models.recruiting import Fee, Placement
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingInvoice,
    StaffingWorker,
)
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService
from tests.api.test_owner_filter import auth_header
from tests.api.test_staffing_api import Crew, crew, make_candidate  # noqa: F401

P = "/api/v1/staffing"
TODAY = date.today()


def _candidate(session_factory: sessionmaker[Session], first: str = "Olga") -> str:
    with session_factory() as session:
        row = Candidate(first_name=first, last_name="Angebot")
        session.add(row)
        session.commit()
        return str(row.id)


def test_offer_creates_the_worker_profile_and_a_planned_assignment(
    client: TestClient, crew: Crew, session_factory: sessionmaker[Session]
) -> None:
    candidate_id = _candidate(session_factory)
    start = (TODAY + timedelta(days=14)).isoformat()
    # nur das Profil (Anwaerter), noch kein Einsatz
    first = client.post(
        f"{P}/offer-from-candidate", json={"candidate_id": candidate_id}, headers=crew.a.headers
    )
    assert first.status_code == 200, first.text
    assert first.json()["worker_created"] is True and first.json()["assignment_id"] is None
    worker = client.get(f"{P}/workers/{first.json()['worker_id']}", headers=crew.a.headers).json()
    assert worker["status"] == "applicant"
    # derselbe Kandidat noch einmal, jetzt mit Kunde und Beginn: Profil wird wiederverwendet
    second = client.post(
        f"{P}/offer-from-candidate",
        json={
            "candidate_id": candidate_id,
            "client_company_id": crew.client_id,
            "start_date": start,
        },
        headers=crew.a.headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["worker_created"] is False
    assignment = client.get(
        f"{P}/assignments/{second.json()['assignment_id']}", headers=crew.a.headers
    ).json()
    assert assignment["status"] == "planned" and assignment["owner_user_id"] == crew.a.id
    assert assignment["start_date"] == start
    # Kunde ohne Beginn (oder umgekehrt) ist unvollstaendig
    for body in (
        {"candidate_id": candidate_id, "client_company_id": crew.client_id},
        {"candidate_id": candidate_id, "start_date": start},
    ):
        assert (
            client.post(f"{P}/offer-from-candidate", json=body, headers=crew.a.headers).status_code
            == 422
        )
    unknown = client.post(
        f"{P}/offer-from-candidate",
        json={"candidate_id": str(uuid.uuid4())},
        headers=crew.a.headers,
    )
    assert unknown.status_code == 404


def test_offer_warns_when_a_colleague_already_works_with_the_candidate(
    client: TestClient, crew: Crew, session_factory: sessionmaker[Session]
) -> None:
    candidate_id = _candidate(session_factory, "Pia")
    with session_factory() as session:
        session.add(
            CandidateSubmission(
                candidate_id=uuid.UUID(candidate_id),
                client_company_id=uuid.UUID(crew.client_id),
                status=SubmissionStatus.INTERVIEW,
                owner_user_id=uuid.UUID(crew.c.id),
            )
        )
        session.commit()
    body = {"candidate_id": candidate_id}
    warned = client.post(f"{P}/offer-from-candidate", json=body, headers=crew.a.headers)
    assert warned.status_code == 409 and "bereits im Austausch" in warned.json()["detail"]
    ok = client.post(
        f"{P}/offer-from-candidate?confirm_engagement=true", json=body, headers=crew.a.headers
    )
    assert ok.status_code == 200, ok.text


def test_offer_needs_the_staffing_view(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        user = User(email="nur-direct@b.example", hashed_password=hash_password("x"), role="member")
        session.add(user)
        session.commit()
        session.add(UserViewAccess(user_id=user.id, view="direct"))
        session.commit()
        _, token = AuthService(session).login("nur-direct@b.example", "x")
    response = client.post(
        f"{P}/offer-from-candidate",
        json={"candidate_id": str(uuid.uuid4())},
        headers=auth_header(token),
    )
    assert response.status_code == 403


def _business_data(session_factory: sessionmaker[Session], crew: Crew) -> None:
    client_id = uuid.UUID(crew.client_id)
    with session_factory() as session:
        c1 = Candidate(first_name="Eva", last_name="Eins")
        c2 = Candidate(first_name="Fritz", last_name="Zwei")
        session.add_all([c1, c2])
        session.flush()
        mine = CandidateSubmission(
            candidate_id=c1.id,
            client_company_id=client_id,
            status=SubmissionStatus.PLACEMENT,
            owner_user_id=uuid.UUID(crew.a.id),
            expected_fee=Decimal("12000"),
        )
        others = CandidateSubmission(
            candidate_id=c2.id,
            client_company_id=client_id,
            status=SubmissionStatus.OFFER,
            owner_user_id=uuid.UUID(crew.c.id),
            expected_fee=Decimal("9000"),
        )
        session.add_all([mine, others])
        session.flush()
        placement = Placement(
            submission_id=mine.id,
            start_date=TODAY,
            final_salary=Decimal("60000"),
            fee_percentage=Decimal("20"),
            calculated_fee=Decimal("12000"),
        )
        session.add(placement)
        session.flush()
        session.add(
            Fee(
                placement_id=placement.id,
                amount_net=Decimal("12000"),
                vat_rate=Decimal("19"),
                amount_gross=Decimal("14280"),
                invoice_status=InvoiceStatus.PAID,
                paid_at=datetime.now(UTC),
            )
        )
        worker = StaffingWorker(candidate_id=c1.id)
        session.add(worker)
        session.flush()
        session.add_all(
            [
                StaffingAssignment(
                    worker_id=worker.id,
                    client_company_id=client_id,
                    owner_user_id=uuid.UUID(crew.a.id),
                    start_date=TODAY - timedelta(days=30),
                    status=StaffingAssignmentStatus.ACTIVE,
                ),
                StaffingAssignment(
                    worker_id=worker.id,
                    client_company_id=client_id,
                    owner_user_id=uuid.UUID(crew.c.id),
                    start_date=TODAY + timedelta(days=30),
                    status=StaffingAssignmentStatus.PLANNED,
                ),
            ]
        )
        session.add(
            StaffingInvoice(
                client_company_id=client_id,
                period_start=TODAY - timedelta(days=30),
                period_end=TODAY,
                amount_net=Decimal("3000"),
                vat_rate=Decimal("19"),
                amount_gross=Decimal("3570"),
                invoice_status=InvoiceStatus.ISSUED,
            )
        )
        session.commit()


def test_client_business_follows_views_scope_and_money_rules(
    client: TestClient, crew: Crew, session_factory: sessionmaker[Session]
) -> None:
    _business_data(session_factory, crew)
    url = f"/api/v1/clients/{crew.client_id}/business"
    admin = client.get(url, headers=crew.admin.headers).json()
    assert len(admin["processes"]) == 2 and len(admin["assignments"]) == 2
    assert Decimal(admin["revenue"]["placement_fees_paid"]) == Decimal("12000")
    assert Decimal(admin["revenue"]["staffing_invoiced"]) == Decimal("3000")
    # Anna (Mitarbeiterin): nur ihre Prozesse und Einsaetze, keine Betraege
    mine = client.get(url, headers=crew.a.headers).json()
    assert [p["candidate_name"] for p in mine["processes"]] == ["Eva Eins"]
    assert len(mine["assignments"]) == 1 and mine["revenue"] is None
    assert mine["deadlines"] is not None
    # Clara (anderer Teamleiter) sieht nur Claras Einsatz/Prozess
    other = client.get(url, headers=crew.c.headers).json()
    assert [p["candidate_name"] for p in other["processes"]] == ["Fritz Zwei"]
    assert len(other["assignments"]) == 1
    # Ohne Ansicht Direct bzw. Ueberlassung fehlen die Abschnitte ganz
    with session_factory() as session:
        for email, views in (("d@b.example", ("direct",)), ("s@b.example", ("staffing",))):
            user = User(email=email, hashed_password=hash_password("x"), role="member")
            session.add(user)
            session.commit()
            for view in views:
                session.add(UserViewAccess(user_id=user.id, view=view))
            session.commit()
        tokens = {
            email: auth_header(AuthService(session).login(email, "x")[1])
            for email in ("d@b.example", "s@b.example")
        }
    only_direct = client.get(url, headers=tokens["d@b.example"]).json()
    assert only_direct["assignments"] is None and only_direct["deadlines"] is None
    assert only_direct["processes"] == []  # Direct ja, aber keine eigenen Prozesse
    only_staffing = client.get(url, headers=tokens["s@b.example"]).json()
    assert only_staffing["processes"] is None and only_staffing["assignments"] == []
    assert (
        client.get(f"/api/v1/clients/{uuid.uuid4()}/business", headers=crew.a.headers).status_code
        == 404
    )
