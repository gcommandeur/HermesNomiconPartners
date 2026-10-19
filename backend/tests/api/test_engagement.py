# NOMICON: gemeinsamer Kandidatenstatus - nur in der Nomicon-Kopie.
"""Wo ist ein Kandidat im Austausch? Jeder Gesamtstatus, Sichtbarkeit fuer Fremde (kein
Kanzleiname), Praeferenzen, Filter, Sammelabfrage ohne N+1, Warn- und Sperrmodus."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.engagement import CandidateEngagementPrefs
from cc_crm.models.enums import SubmissionStatus
from cc_crm.models.recruiting import AuditLog, Placement
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingWorker,
)
from cc_crm.models.submission import CandidateSubmission
from tests.api.test_team_lead import Person, _make_user

API = "/api/v1"
SECRET_CLIENT = "Geheime Kanzlei Rheinblick GmbH"
TODAY = date.today()


@dataclass
class World:
    admin: Person
    anna: Person  # Mitarbeiterin (Direct-Betreuerin)
    ben: Person  # Mitarbeiter (Disponent), kein Team von Anna
    client_id: str


@pytest.fixture
def world(client: TestClient, session_factory: sessionmaker[Session]) -> World:
    admin = _make_user(session_factory, "gf@e.example", "admin", "Gerda GF")
    anna = _make_user(session_factory, "anna@e.example", "member", "Anna K.")
    ben = _make_user(session_factory, "ben@e.example", "member", "Ben S.")
    with session_factory() as session:
        company = ClientCompany(name=SECRET_CLIENT)
        session.add(company)
        session.commit()
        return World(admin=admin, anna=anna, ben=ben, client_id=str(company.id))


def _candidate(session_factory: sessionmaker[Session], first: str = "Mira") -> uuid.UUID:
    with session_factory() as session:
        row = Candidate(first_name=first, last_name="Muster")
        session.add(row)
        session.commit()
        return row.id


def _process(
    session_factory: sessionmaker[Session],
    world: World,
    candidate_id: uuid.UUID,
    owner: Person,
    status: SubmissionStatus = SubmissionStatus.INTERVIEW,
    *,
    archived: bool = False,
) -> uuid.UUID:
    with session_factory() as session:
        row = CandidateSubmission(
            candidate_id=candidate_id,
            client_company_id=uuid.UUID(world.client_id),
            status=status,
            owner_user_id=uuid.UUID(owner.id),
            last_activity_at=datetime(2026, 10, 3, tzinfo=UTC),
            archived_at=datetime(2026, 10, 4, tzinfo=UTC) if archived else None,
        )
        session.add(row)
        session.commit()
        if status == SubmissionStatus.PLACEMENT:
            session.add(
                Placement(
                    submission_id=row.id,
                    start_date=date(2026, 11, 1),
                    final_salary=60000,
                    fee_percentage=20,
                    calculated_fee=12000,
                )
            )
            session.commit()
        return row.id


def _assignment(
    session_factory: sessionmaker[Session],
    world: World,
    candidate_id: uuid.UUID,
    owner: Person,
    status: StaffingAssignmentStatus = StaffingAssignmentStatus.ACTIVE,
) -> uuid.UUID:
    with session_factory() as session:
        worker = session.scalar(
            select(StaffingWorker).where(StaffingWorker.candidate_id == candidate_id)
        )
        if worker is None:
            worker = StaffingWorker(candidate_id=candidate_id)
            session.add(worker)
            session.commit()
        row = StaffingAssignment(
            worker_id=worker.id,
            client_company_id=uuid.UUID(world.client_id),
            owner_user_id=uuid.UUID(owner.id),
            start_date=TODAY - timedelta(days=10),
            planned_end_date=TODAY + timedelta(days=60),
            status=status,
        )
        session.add(row)
        session.commit()
        return row.id


def _status(client: TestClient, who: Person, candidate_id: uuid.UUID) -> dict:
    response = client.get(f"{API}/candidates/{candidate_id}/engagement", headers=who.headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_free_candidate_and_preferences(
    client: TestClient, world: World, session_factory: sessionmaker[Session]
) -> None:
    cid = _candidate(session_factory)
    body = _status(client, world.anna, cid)
    assert body["status"] == "frei"
    assert body["items"] == []
    assert (body["open_for_direct"], body["open_for_staffing"]) == ("unknown", "unknown")

    changed = client.patch(
        f"{API}/candidates/{cid}/engagement-prefs",
        json={"open_for_staffing": "yes", "open_for_direct": "no"},
        headers=world.ben.headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["open_for_staffing"] == "yes"
    assert changed.json()["open_for_direct"] == "no"
    with session_factory() as session:
        entries = session.scalars(
            select(AuditLog).where(AuditLog.entity_type == "candidate_engagement_prefs")
        ).all()
        assert len(entries) == 1 and entries[0].changed_by == "ben@e.example"
    bad = client.patch(
        f"{API}/candidates/{cid}/engagement-prefs",
        json={"open_for_direct": "vielleicht"},
        headers=world.ben.headers,
    )
    assert bad.status_code == 422
    missing = client.patch(
        f"{API}/candidates/{uuid.uuid4()}/engagement-prefs",
        json={"open_for_direct": "yes"},
        headers=world.ben.headers,
    )
    assert missing.status_code == 404
    assert (
        client.get(
            f"{API}/candidates/{uuid.uuid4()}/engagement", headers=world.ben.headers
        ).status_code
        == 404
    )


def test_every_overall_status(
    client: TestClient, world: World, session_factory: sessionmaker[Session]
) -> None:
    direct = _candidate(session_factory, "Dora")
    _process(session_factory, world, direct, world.anna)
    staffing = _candidate(session_factory, "Emil")
    _assignment(session_factory, world, staffing, world.ben)
    both = _candidate(session_factory, "Fay")
    _process(session_factory, world, both, world.anna, SubmissionStatus.CV_OUT)
    _assignment(session_factory, world, both, world.ben, StaffingAssignmentStatus.PLANNED)
    placed = _candidate(session_factory, "Gil")
    _process(session_factory, world, placed, world.anna, SubmissionStatus.PLACEMENT, archived=True)
    _assignment(session_factory, world, placed, world.ben)  # Vermittlung geht vor
    # zaehlt NICHT: abgebrochen, archivierter Prozess ohne Placement, beendeter Einsatz
    ghost = _candidate(session_factory, "Hanna")
    _process(session_factory, world, ghost, world.anna, SubmissionStatus.CANCELLED)
    _process(session_factory, world, ghost, world.anna, SubmissionStatus.OFFER, archived=True)
    _assignment(session_factory, world, ghost, world.ben, StaffingAssignmentStatus.ENDED)

    assert _status(client, world.admin, direct)["status"] == "im_direct"
    assert _status(client, world.admin, staffing)["status"] == "im_einsatz"
    assert _status(client, world.admin, both)["status"] == "beides"
    assert _status(client, world.admin, placed)["status"] == "vermittelt"
    assert _status(client, world.admin, ghost)["status"] == "frei"


def test_foreign_processes_show_channel_stage_client_owner_and_date_but_no_ids(
    client: TestClient, world: World, session_factory: sessionmaker[Session]
) -> None:
    cid = _candidate(session_factory)
    submission_id = _process(session_factory, world, cid, world.anna)
    assignment_id = _assignment(session_factory, world, cid, world.ben)

    own_direct = _status(client, world.anna, cid)
    direct_item = next(i for i in own_direct["items"] if i["channel"] == "direct")
    assert direct_item["details_visible"] is True
    assert direct_item["client_name"] == SECRET_CLIENT
    assert direct_item["entity_id"] == str(submission_id)
    staffing_item = next(i for i in own_direct["items"] if i["channel"] == "staffing")
    assert staffing_item["details_visible"] is False  # Annas Sicht auf Bens Einsatz

    # Ben sieht Annas Prozess nur grob
    response = client.get(f"{API}/candidates/{cid}/engagement", headers=world.ben.headers)
    assert str(submission_id) not in response.text
    item = next(i for i in response.json()["items"] if i["channel"] == "direct")
    assert item == {
        "channel": "direct",
        "kind": "process",
        "stage": "interview",
        "owner_name": "Anna K.",
        "since": "2026-10-03",
        "until": None,
        "details_visible": False,
        "client_name": SECRET_CLIENT,
        "entity_id": None,
    }
    # ...und Annas Sicht auf Bens Einsatz ebenfalls (Sammelabfrage)
    summary = client.post(
        f"{API}/engagement/summary", json={"candidate_ids": [str(cid)]}, headers=world.anna.headers
    )
    assert SECRET_CLIENT in summary.text  # eigener Prozess: Kanzlei sichtbar
    assert str(assignment_id) not in summary.text  # Bens Einsatz: keine ID, keine Details
    # Admin sieht alles
    admin_items = _status(client, world.admin, cid)["items"]
    assert all(entry["details_visible"] for entry in admin_items)
    # Kein Lohn, keine Marge in der Antwort
    assert "wage" not in response.text and "billing" not in response.text


def test_summary_uses_a_constant_number_of_queries(
    client: TestClient, world: World, session_factory: sessionmaker[Session]
) -> None:
    ids = []
    for index in range(30):
        cid = _candidate(session_factory, f"K{index}")
        ids.append(str(cid))
        if index % 2:
            _process(session_factory, world, cid, world.anna)
        if index % 3 == 0:
            _assignment(session_factory, world, cid, world.ben)
    bind = session_factory.kw["bind"]
    counted: list[str] = []

    def count(_conn, _cursor, statement, *_rest) -> None:  # type: ignore[no-untyped-def]
        if statement.lstrip().upper().startswith("SELECT"):
            counted.append(statement)

    def run(subset: list[str]) -> int:
        counted.clear()
        response = client.post(
            f"{API}/engagement/summary", json={"candidate_ids": subset}, headers=world.ben.headers
        )
        assert response.status_code == 200 and len(response.json()) == len(subset)
        return len(counted)

    event.listen(bind, "before_cursor_execute", count)
    try:
        small = run(ids[:3])
        large = run(ids)
    finally:
        event.remove(bind, "before_cursor_execute", count)
    assert large == small, (small, large)  # nicht mit der Anzahl der Kandidaten gewachsen
    assert large <= 12, large


def test_candidate_list_filters(
    client: TestClient, world: World, session_factory: sessionmaker[Session]
) -> None:
    engaged = _candidate(session_factory, "Ina")
    _process(session_factory, world, engaged, world.anna)
    declined = _candidate(session_factory, "Jan")
    with session_factory() as session:
        session.add(
            CandidateEngagementPrefs(
                candidate_id=declined, open_for_direct="no", open_for_staffing="yes"
            )
        )
        session.commit()
    free = _candidate(session_factory, "Kim")
    in_staffing = _candidate(session_factory, "Lea")
    _assignment(session_factory, world, in_staffing, world.ben)

    def names(filter_name: str) -> set[str]:
        response = client.get(
            f"{API}/candidates?engagement={filter_name}&limit=100", headers=world.anna.headers
        )
        assert response.status_code == 200, response.text
        return {row["first_name"] for row in response.json()["items"]}

    assert names("engaged") == {"Ina", "Lea"}
    assert names("free_direct") == {"Kim", "Lea"}  # Jan lehnt Direct ab, Ina ist im Prozess
    assert names("free_staffing") == {"Ina", "Jan", "Kim"}  # Lea ist im Einsatz
    assert free  # Kim steht in beiden "frei"-Listen


def test_warn_confirm_and_block_modes_when_creating_a_process(
    client: TestClient, world: World, session_factory: sessionmaker[Session]
) -> None:
    cid = _candidate(session_factory)
    _process(session_factory, world, cid, world.ben)  # Kollege betreut den Kandidaten bereits
    # andere Kanzlei als Bens Prozess (derselbe Kandidat bei derselben Kanzlei waere bereits ein
    # Duplikat in Hermes' eigener Pruefung)
    body = {"candidate_id": str(cid), "client_company_id": _second_client(session_factory)}

    warned = client.post(f"{API}/submissions", json=body, headers=world.anna.headers)
    assert warned.status_code == 409, warned.text
    assert "bereits im Austausch" in warned.json()["detail"]
    assert "Ben S." in warned.json()["detail"]
    assert SECRET_CLIENT in warned.json()["detail"]  # Kunde sichtbar
    confirmed = client.post(
        f"{API}/submissions?confirm_engagement=true", json=body, headers=world.anna.headers
    )
    assert confirmed.status_code == 201, confirmed.text

    # Annas eigener Prozess zaehlt jetzt, ein weiterer eigener loest nichts aus - Bens aber schon
    third_body = {"candidate_id": str(cid), "client_company_id": _second_client(session_factory)}
    third = client.post(f"{API}/submissions", json=third_body, headers=world.anna.headers)
    assert third.status_code == 409  # Bens Prozess besteht weiter
    assert "bereits im Austausch" in third.json()["detail"]

    # Sperrmodus (Admin-Einstellung): auch mit Bestaetigung nicht
    assert client.get(f"{API}/admin/engagement-settings", headers=world.admin.headers).json() == {
        "conflict_mode": "warn"
    }
    assert (
        client.put(
            f"{API}/admin/engagement-settings",
            json={"conflict_mode": "block"},
            headers=world.anna.headers,
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"{API}/admin/engagement-settings",
            json={"conflict_mode": "block"},
            headers=world.admin.headers,
        ).status_code
        == 200
    )
    blocked = client.post(
        f"{API}/submissions?confirm_engagement=true", json=third_body, headers=world.anna.headers
    )
    assert blocked.status_code == 422
    assert "gesperrt" in blocked.json()["detail"]


def test_own_parallel_processes_and_free_candidates_pass_without_warning(
    client: TestClient, world: World, session_factory: sessionmaker[Session]
) -> None:
    free = _candidate(session_factory, "Mo")
    body = {"candidate_id": str(free), "client_company_id": world.client_id}
    assert (
        client.post(f"{API}/submissions", json=body, headers=world.anna.headers).status_code == 201
    )
    # derselbe Mitarbeiter, weiterer Prozess beim selben Kandidaten: Alltag, keine Warnung
    other_company = _second_client(session_factory)
    second = {"candidate_id": str(free), "client_company_id": other_company}
    assert (
        client.post(f"{API}/submissions", json=second, headers=world.anna.headers).status_code
        == 201
    )


def _second_client(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        row = ClientCompany(name=f"Andere Kanzlei {uuid.uuid4().hex[:6]} AG")
        session.add(row)
        session.commit()
        return str(row.id)


def test_creating_an_assignment_for_a_candidate_in_a_direct_process_warns(
    client: TestClient, world: World, session_factory: sessionmaker[Session]
) -> None:
    cid = _candidate(session_factory)
    _process(session_factory, world, cid, world.anna)
    with session_factory() as session:
        worker = StaffingWorker(candidate_id=cid)
        session.add(worker)
        session.commit()
        worker_id = str(worker.id)
    body = {
        "worker_id": worker_id,
        "client_company_id": world.client_id,
        "start_date": (TODAY + timedelta(days=5)).isoformat(),
    }
    warned = client.post(f"{API}/staffing/assignments", json=body, headers=world.ben.headers)
    assert warned.status_code == 409, warned.text
    assert f"Direct: Interview bei {SECRET_CLIENT} (Anna K.)" in warned.json()["detail"]
    ok = client.post(
        f"{API}/staffing/assignments?confirm_engagement=true", json=body, headers=world.ben.headers
    )
    assert ok.status_code == 201, ok.text


def test_requires_login(client: TestClient) -> None:
    anonymous = {"Authorization": ""}
    cid = uuid.uuid4()
    assert client.get(f"{API}/candidates/{cid}/engagement", headers=anonymous).status_code == 401
    assert (
        client.post(
            f"{API}/engagement/summary", json={"candidate_ids": []}, headers=anonymous
        ).status_code
        == 401
    )


def test_client_name_of_foreign_processes_stays_out_of_history_and_comments_only(
    client: TestClient, world: World, session_factory: sessionmaker[Session]
) -> None:
    cid = _candidate(session_factory)
    created = client.post(
        f"{API}/submissions",
        json={"candidate_id": str(cid), "client_company_id": world.client_id},
        headers=world.anna.headers,
    )
    assert created.status_code == 201, created.text
    for path in ("history", "comments"):
        response = client.get(f"{API}/candidates/{cid}/{path}", headers=world.ben.headers)
        assert response.status_code == 200, (path, response.text)
        assert SECRET_CLIENT not in response.text, path
    # im Kandidatenstatus ist der Kunde dagegen bewusst fuer alle sichtbar (Nutzerentscheid)
    status = client.get(f"{API}/candidates/{cid}/engagement", headers=world.ben.headers)
    assert SECRET_CLIENT in status.text


def test_channel_must_be_ticked_at_the_candidate(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Überlassung braucht ein ausdrückliches Ja, Direct ist nur bei Nein gesperrt."""
    from cc_crm.core.errors import BusinessRuleError
    from cc_crm.services.engagement_status import require_channel_open

    with session_factory() as session:
        candidate = Candidate(first_name="Kai", last_name="Kanal")
        session.add(candidate)
        session.commit()
        cid = candidate.id
        require_channel_open(session, cid, "direct")  # nicht geklärt: erlaubt
        with pytest.raises(BusinessRuleError, match="Überlassung"):
            require_channel_open(session, cid, "staffing")
        session.add(CandidateEngagementPrefs(candidate_id=cid, open_for_direct="no"))
        session.commit()
        with pytest.raises(BusinessRuleError, match="Direct"):
            require_channel_open(session, cid, "direct")
