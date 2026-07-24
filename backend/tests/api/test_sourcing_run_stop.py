import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.enums import SourcingRunStatus, SourcingSourceType
from cc_crm.schemas.sourcing import SourcingRunResult
from cc_crm.services.sourcing import SourcingService, scan_team_pages_in_background


def test_status_is_null_when_no_run_ever_started(client: TestClient) -> None:
    response = client.get("/api/v1/sourcing/status")

    assert response.status_code == 200
    assert response.json() is None


def test_stop_without_active_run_returns_404(client: TestClient) -> None:
    response = client.post("/api/v1/sourcing/stop", json={})

    assert response.status_code == 404


def test_start_run_then_status_reflects_running(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        run = SourcingService(session).start_run(SourcingSourceType.KANZLEI_TEAM_PAGE, total=5)
        run_id = run.id

    response = client.get("/api/v1/sourcing/status")
    body = response.json()
    assert body["id"] == str(run_id)
    assert body["status"] == "running"
    assert body["total"] == 5
    assert body["processed"] == 0
    assert body["stop_requested"] is False


def test_stop_sets_flag_and_run_stops_before_next_company(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kernverhalten des Stop-Mechanismus: nach POST /sourcing/stop bricht der
    Hintergrund-Lauf VOR der naechsten Kanzlei ab, statt weiter LLM-Aufrufe zu
    machen (siehe scan_team_pages_in_background-Docstring) - hier real gegen
    die (Test-)DB verifiziert, nicht gemockt."""
    # scan_team_pages_in_background importiert SessionLocal lokal (Aufruf-
    # zeitpunkt, um einen Zirkelimport zu vermeiden) - fuer den Test daher am
    # Ursprungsmodul auf die Test-DB-Session-Factory umbiegen.
    monkeypatch.setattr("cc_crm.infrastructure.database.session.SessionLocal", session_factory)

    call_count = 0

    def fake_scrape(_client_company_id: uuid.UUID) -> SourcingRunResult:
        nonlocal call_count
        call_count += 1
        # Stop wird "waehrend" die erste Kanzlei laeuft angefordert, simuliert
        # per direktem Service-Call (entspricht dem echten Stop-Endpunkt).
        with session_factory() as session:
            SourcingService(session).request_stop()
        return SourcingRunResult(found=1, created=1)

    monkeypatch.setattr(
        SourcingService, "run_kanzlei_team_scrape", lambda self, cid: fake_scrape(cid)
    )

    company_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    with session_factory() as session:
        run = SourcingService(session).start_run(
            SourcingSourceType.KANZLEI_TEAM_PAGE, total=len(company_ids)
        )
        run_id = run.id

    scan_team_pages_in_background(company_ids, run_id)

    # Nur die erste Kanzlei wurde verarbeitet (dabei kam der Stop rein) -
    # die zweite/dritte wurden NICHT mehr angefasst.
    assert call_count == 1

    with session_factory() as session:
        final_run = SourcingService(session).get_run_status()
        assert final_run is not None
        assert final_run.id == run_id
        assert final_run.status == SourcingRunStatus.STOPPED
        assert final_run.processed == 1
        assert final_run.leads_created == 1
        assert final_run.finished_at is not None


def test_run_completes_normally_when_never_stopped(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cc_crm.infrastructure.database.session.SessionLocal", session_factory)
    monkeypatch.setattr(
        SourcingService,
        "run_kanzlei_team_scrape",
        lambda self, cid: SourcingRunResult(found=1, created=1),
    )

    company_ids = [uuid.uuid4(), uuid.uuid4()]
    with session_factory() as session:
        run = SourcingService(session).start_run(
            SourcingSourceType.KANZLEI_TEAM_PAGE, total=len(company_ids)
        )
        run_id = run.id

    scan_team_pages_in_background(company_ids, run_id)

    with session_factory() as session:
        final_run = SourcingService(session).get_run_status()
        assert final_run is not None
        assert final_run.status == SourcingRunStatus.COMPLETED
        assert final_run.processed == 2
        assert final_run.leads_created == 2
