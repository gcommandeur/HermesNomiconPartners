"""Überlassung am Kandidaten: Spalte (Sammelabfrage), Filter der Liste, Stundenzettel-Status,
Rechte (Ansicht, Besitzbereich, kein Lohn/Marge) und Laufzeit bei vielen Kandidaten."""

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.access_views import UserViewAccess
from cc_crm.models.candidate import Candidate
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingWorker,
    StaffingWorkerStatus,
)
from tests.api.test_staffing_api import (  # noqa: F401
    Crew,
    _assignment,
    _license,
    _worker,
    crew,
    make_candidate,
)

P = "/api/v1/staffing"
TODAY = date.today()


def _summary(client: TestClient, who, ids: list[str]) -> dict[str, dict]:  # type: ignore[no-untyped-def]
    response = client.post(
        f"{P}/candidate-summary", json={"candidate_ids": ids}, headers=who.headers
    )
    assert response.status_code == 200, response.text
    return {row["candidate_id"]: row for row in response.json()}


def _list(client: TestClient, who, **params) -> list[str]:  # type: ignore[no-untyped-def]
    response = client.get(
        "/api/v1/candidates", params={"limit": 500, **params}, headers=who.headers
    )
    assert response.status_code == 200, response.text
    return [row["id"] for row in response.json()["items"]]


def test_summary_and_list_filters(client: TestClient, crew: Crew, make_candidate) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    _license(client, crew)
    plain = make_candidate("Plain")
    applicant = make_candidate("Anwaerter")
    bench = make_candidate("Bench")
    placed = make_candidate("Einsatz")
    _worker(client, crew.admin, applicant)
    long_ago = str(TODAY - timedelta(days=400))
    bench_worker = _worker(client, crew.admin, bench, status="active", entry_date=long_ago)
    placed_worker = _worker(client, crew.admin, placed, status="active", entry_date=long_ago)
    started = str(TODAY - timedelta(days=5))
    _assignment(client, crew.a, placed_worker["id"], crew.client_id, start_date=started)
    ids = [plain, applicant, bench, placed]
    summaries = _summary(client, crew.a, ids)
    assert summaries[plain]["status"] == "none"
    assert summaries[applicant]["status"] == "applicant" and not summaries[applicant]["bench"]
    assert summaries[bench]["status"] == "active" and summaries[bench]["bench"] is True
    assert summaries[placed]["status"] == "active" and not summaries[placed]["bench"]
    assert summaries[placed]["assignment_status"] == "planned"
    assert summaries[placed]["client_name"]
    assert bench_worker["id"]
    # keine Lohn-/Margenangaben
    text = client.post(
        f"{P}/candidate-summary", json={"candidate_ids": ids}, headers=crew.admin.headers
    ).text
    for forbidden in ("wage", "billing", "margin", "rate"):
        assert forbidden not in text.replace("assignment_status", ""), forbidden

    assert set(_list(client, crew.a, staffing="workers")) == {applicant, bench, placed}
    assert _list(client, crew.a, staffing="applicants") == [applicant]
    assert _list(client, crew.a, staffing="bench") == [bench]
    assert plain in _list(client, crew.a)  # bestehende Liste unverändert


def test_filter_and_summary_need_the_staffing_view(
    client: TestClient, crew: Crew, session_factory: sessionmaker[Session], make_candidate  # noqa: F811
) -> None:  # type: ignore[no-untyped-def]
    candidate = make_candidate("Sichtbar")
    with session_factory() as session:
        for row in session.query(UserViewAccess).filter(
            UserViewAccess.user_id == uuid.UUID(crew.a.id), UserViewAccess.view == "staffing"
        ):
            session.delete(row)
        session.commit()
    denied = client.get("/api/v1/candidates?staffing=bench", headers=crew.a.headers)
    assert denied.status_code == 403 and "nicht freigeschaltet" in denied.json()["detail"]
    assert client.post(
        f"{P}/candidate-summary", json={"candidate_ids": [candidate]}, headers=crew.a.headers
    ).status_code == 403
    # die normale Liste bleibt für alle nutzbar
    assert candidate in _list(client, crew.a)


def test_creating_the_worker_from_a_candidate_never_duplicates(
    client: TestClient, crew: Crew, make_candidate  # noqa: F811
) -> None:  # type: ignore[no-untyped-def]
    candidate = make_candidate("Einmalig")
    _worker(client, crew.a, candidate)
    again = client.post(f"{P}/workers", json={"candidate_id": candidate}, headers=crew.a.headers)
    assert again.status_code == 409
    found = client.get(f"{P}/workers/by-candidate/{candidate}", headers=crew.a.headers)
    assert found.status_code == 200 and found.json()["candidate_id"] == candidate


def test_worker_timesheet_summary_follows_the_owner_scope(
    client: TestClient, crew: Crew, make_candidate  # noqa: F811
) -> None:  # type: ignore[no-untyped-def]
    _license(client, crew)
    worker = _worker(client, crew.a, make_candidate("Zettel"))
    own = client.get(f"{P}/workers/{worker['id']}/timesheet-summary", headers=crew.a.headers)
    assert own.status_code == 200
    assert own.json() == {
        "worker_id": worker["id"],
        "open": 0,
        "submitted": 0,
        "approved": 0,
        "rejected": 0,
        "approved_unbilled": 0,
    }
    missing = client.get(f"{P}/workers/{uuid.uuid4()}/timesheet-summary", headers=crew.a.headers)
    assert missing.status_code == 404


def test_summary_has_constant_queries_and_scales_to_thousands_of_candidates(
    client: TestClient, crew: Crew, session_factory: sessionmaker[Session]  # noqa: F811
) -> None:
    """2.900 Kandidaten, 300 Leiharbeitnehmer, 200 offene Einsätze: Spalte und Filter ohne N+1."""
    with session_factory() as session:
        candidates = [Candidate(first_name=f"K{i}", last_name="Last") for i in range(2900)]
        session.add_all(candidates)
        session.flush()
        workers = [
            StaffingWorker(candidate_id=c.id, status=StaffingWorkerStatus.ACTIVE)
            for c in candidates[:300]
        ]
        session.add_all(workers)
        session.flush()
        for worker in workers[:200]:
            session.add(
                StaffingAssignment(
                    worker_id=worker.id,
                    client_company_id=uuid.UUID(crew.client_id),
                    owner_user_id=uuid.UUID(crew.a.id),
                    start_date=TODAY - timedelta(days=30),
                    status=StaffingAssignmentStatus.ACTIVE,
                )
            )
        session.commit()
        ids = [str(c.id) for c in candidates]
    bind = session_factory.kw["bind"]
    counted: list[str] = []

    def count(_conn, _cursor, statement, *_rest) -> None:  # type: ignore[no-untyped-def]
        if statement.lstrip().upper().startswith("SELECT"):
            counted.append(statement)

    def run(subset: list[str]) -> int:
        counted.clear()
        response = client.post(
            f"{P}/candidate-summary", json={"candidate_ids": subset}, headers=crew.a.headers
        )
        assert response.status_code == 200 and len(response.json()) == len(subset)
        return len(counted)

    event.listen(bind, "before_cursor_execute", count)
    try:
        small = run(ids[:5])
        page = run(ids[:100])
        everything = run(ids[:500])
    finally:
        event.remove(bind, "before_cursor_execute", count)
    assert small <= page + 1 and everything <= page + 1, (small, page, everything)
    assert everything <= 12, everything
    assert len(_list(client, crew.a, staffing="workers")) == 300
    assert len(_list(client, crew.a, staffing="bench")) == 100
