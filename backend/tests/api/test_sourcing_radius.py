"""Umkreissuche im Sourcing fuer jede Quelle: Verzeichnis-Quellen fragen alle
PLZ im Umkreis ab, der Kanzlei-Team-Scan nimmt nur Kanzleien im Umkreis.
Beides laeuft als Hintergrund-Lauf mit Fortschritt/Stop."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.enums import SourcingRunStatus
from cc_crm.models.postal_locality import PostalLocality
from cc_crm.schemas.sourcing import SourcingRunResult
from cc_crm.services.sourcing import SourcingService
from tests.jobs import drain_jobs

EMPTY_DIRECTORY_HTML = "<html><body></body></html>"


@pytest.fixture
def stuttgart_and_munich(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    with session_factory() as session:
        session.add_all(
            [
                PostalLocality(
                    postal_code="70191", locality="Stuttgart", latitude=48.7900, longitude=9.1900
                ),
                PostalLocality(
                    postal_code="70173", locality="Stuttgart", latitude=48.7760, longitude=9.1770
                ),
                PostalLocality(
                    postal_code="70372", locality="Stuttgart", latitude=48.8050, longitude=9.2150
                ),
                PostalLocality(
                    postal_code="80331", locality="München", latitude=48.1370, longitude=11.5750
                ),
            ]
        )
        session.commit()
    # Hintergrund-Lauf oeffnet eine eigene Session - auf die Test-DB umbiegen.
    monkeypatch.setattr("cc_crm.infrastructure.database.session.SessionLocal", session_factory)
    monkeypatch.setattr("cc_crm.services.sourcing.time.sleep", lambda seconds: None)


@pytest.mark.parametrize(
    ("source_type", "patch_target", "fake_response"),
    [
        (
            "steuerberaterverzeichnis",
            "cc_crm.services.steuerberater_verzeichnis.fetch_search_html",
            EMPTY_DIRECTORY_HTML,
        ),
        ("wpk_berufsregister", "cc_crm.services.wpk_berufsregister.fetch_search_results", []),
    ],
)
@pytest.mark.usefixtures("stuttgart_and_munich")
def test_radius_run_queries_every_postal_code_in_radius_nearest_first(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    source_type: str,
    patch_target: str,
    fake_response: object,
) -> None:
    queried: list[str] = []

    def fake_fetch(plz_or_ort: str) -> object:
        queried.append(plz_or_ort)
        return fake_response

    monkeypatch.setattr(patch_target, fake_fetch)

    response = client.post(
        "/api/v1/sourcing/run",
        json={"source_type": source_type, "center": "70191", "radius_km": 25},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["background_started"] == 3
    assert body["run_id"] is not None
    drain_jobs(session_factory)
    assert queried == ["70191", "70173", "70372"]
    with session_factory() as session:
        run = SourcingService(session).get_run_status()
        assert run is not None
        assert run.status == SourcingRunStatus.COMPLETED
        assert run.total == 3
        assert run.processed == 3


@pytest.mark.usefixtures("stuttgart_and_munich")
def test_radius_run_team_scan_only_scans_companies_in_radius(
    client: TestClient, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    def create_client(name: str, postal_code: str, city: str, website: str | None) -> str:
        response = client.post(
            "/api/v1/clients",
            json={"name": name, "postal_code": postal_code, "city": city, "website": website},
        )
        assert response.status_code == 201, response.text
        return str(response.json()["id"])

    near = create_client("Nah StBG", "70173", "Stuttgart", "https://nah.example")
    create_client("Fern StBG", "80331", "München", "https://fern.example")
    create_client("Ohne Website StBG", "70372", "Stuttgart", None)

    scanned: list[str] = []

    def fake_scrape(_self: SourcingService, company_id: uuid.UUID) -> SourcingRunResult:
        scanned.append(str(company_id))
        return SourcingRunResult()

    monkeypatch.setattr(SourcingService, "run_kanzlei_team_scrape", fake_scrape)

    response = client.post(
        "/api/v1/sourcing/run",
        json={"source_type": "kanzlei_team_page", "center": "70191", "radius_km": 25},
    )

    assert response.status_code == 200, response.text
    assert response.json()["background_started"] == 1
    drain_jobs(session_factory)
    assert scanned == [near]


@pytest.mark.usefixtures("stuttgart_and_munich")
def test_radius_run_with_unresolvable_center_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sourcing/run",
        json={"source_type": "steuerberaterverzeichnis", "center": "Nirgendwo", "radius_km": 25},
    )

    assert response.status_code == 422
    assert "Nirgendwo" in response.json()["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        {"source_type": "steuerberaterverzeichnis", "center": "70191"},
        {"source_type": "steuerberaterverzeichnis", "radius_km": 25},
        {"source_type": "steuerberaterverzeichnis", "center": "70191", "radius_km": 100},
    ],
)
def test_radius_run_requires_center_and_radius_together_and_caps_radius(
    client: TestClient, payload: dict[str, object]
) -> None:
    assert client.post("/api/v1/sourcing/run", json=payload).status_code == 422
