"""Sourcing-Agent Phase 1: Review-Workflow (Lead anlegen, Duplikat-Abgleich
gegen bestehende Kandidaten, approve/reject)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.enums import SourcingLeadStatus, SourcingSourceType
from cc_crm.schemas.sourcing import SourcingLeadCreate
from cc_crm.services.sourcing import SourcingService, normalize_person_name


def make_lead_payload(**overrides: object) -> SourcingLeadCreate:
    values: dict[str, object] = {
        "source_type": SourcingSourceType.STEUERBERATERVERZEICHNIS,
        "source_url": "https://steuerberaterverzeichnis.berufs-org.de/",
        "first_name": "Erika",
        "last_name": "Beispiel",
        "current_employer": "Beispiel & Partner StBG",
        "city": "Stuttgart",
        "postal_code": "70173",
    }
    values.update(overrides)
    return SourcingLeadCreate.model_validate(values)


def test_normalize_person_name_token_sort_and_titles() -> None:
    assert normalize_person_name("Hans", "Müller") == normalize_person_name("Mueller", "Hans")
    assert normalize_person_name("Dr. Hans", "Müller") == normalize_person_name("Hans", "Müller")
    assert normalize_person_name("Erika", "Beispiel") != normalize_person_name("Max", "Beispiel")


def test_create_lead_and_list_pending(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        lead = SourcingService(session).create_lead(make_lead_payload())
    assert lead is not None
    assert lead.status == SourcingLeadStatus.PENDING

    response = client.get("/api/v1/sourcing/leads?status=pending")
    assert response.status_code == 200
    page = response.json()
    assert page["total_count"] == 1
    assert page["items"][0]["first_name"] == "Erika"
    assert page["items"][0]["source_type"] == "steuerberaterverzeichnis"


def test_create_lead_skips_repeated_run_duplicate(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = SourcingService(session)
        assert service.create_lead(make_lead_payload()) is not None
        # Zweiter Lauf, gleiche Person, gleiche Quelle -> kein zweiter Lead.
        assert service.create_lead(make_lead_payload()) is None
        # Auch mit Titel/vertauschter Schreibweise als dieselbe Person erkannt.
        assert (
            service.create_lead(make_lead_payload(first_name="Dr. Erika", last_name="Beispiel"))
            is None
        )
        # Andere Quelle darf einen eigenen Lead anlegen.
        other_source = service.create_lead(
            make_lead_payload(source_type=SourcingSourceType.KANZLEI_TEAM_PAGE)
        )
        assert other_source is not None


def test_existing_candidate_marks_lead_as_possible_duplicate(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    created = client.post(
        "/api/v1/candidates",
        json={"first_name": "Hans", "last_name": "Müller", "city": "Köln"},
    )
    assert created.status_code == 201
    candidate_id = created.json()["id"]

    with session_factory() as session:
        # Verzeichnis-Schreibweise weicht ab (Titel, ue statt ü) - muss
        # trotzdem als moegliches Duplikat erkannt werden.
        lead = SourcingService(session).create_lead(
            make_lead_payload(first_name="Dr. Hans", last_name="Mueller")
        )
    assert lead is not None
    assert lead.status == SourcingLeadStatus.POSSIBLE_DUPLICATE
    assert str(lead.duplicate_of_candidate_id) == candidate_id

    response = client.get("/api/v1/sourcing/leads?status=possible_duplicate")
    assert response.json()["total_count"] == 1


def test_unrelated_candidate_does_not_trigger_duplicate(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    assert (
        client.post(
            "/api/v1/candidates",
            json={"first_name": "Sabine", "last_name": "Schulze-Wettberg"},
        ).status_code
        == 201
    )
    with session_factory() as session:
        lead = SourcingService(session).create_lead(make_lead_payload())
    assert lead is not None
    assert lead.status == SourcingLeadStatus.PENDING
    assert lead.duplicate_of_candidate_id is None


def test_approve_lead_creates_candidate_via_candidate_service(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        lead = SourcingService(session).create_lead(make_lead_payload())
        assert lead is not None

    response = client.post(f"/api/v1/sourcing/leads/{lead.id}/approve")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["created_candidate_id"] is not None
    assert body["reviewed_at"] is not None
    assert body["reviewed_by_user_id"] is not None

    candidate = client.get(f"/api/v1/candidates/{body['created_candidate_id']}").json()
    assert candidate["first_name"] == "Erika"
    assert candidate["last_name"] == "Beispiel"
    assert candidate["city"] == "Stuttgart"
    # Kandidatennummer wird ueber die regulaere CandidateService-Logik vergeben.
    assert candidate["candidate_number"] is not None
    assert "steuerberaterverzeichnis" in (candidate["summary"] or "")

    # Bereits bearbeitete Leads koennen nicht erneut bearbeitet werden.
    again = client.post(f"/api/v1/sourcing/leads/{lead.id}/approve")
    assert again.status_code == 422


def test_reject_lead(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        lead = SourcingService(session).create_lead(make_lead_payload())
        assert lead is not None

    response = client.post(f"/api/v1/sourcing/leads/{lead.id}/reject")
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"

    # Verworfener Lead taucht in der pending-Liste nicht mehr auf.
    assert client.get("/api/v1/sourcing/leads?status=pending").json()["total_count"] == 0


def test_sourcing_routes_require_auth(client: TestClient) -> None:
    client.headers.pop("Authorization")
    assert client.get("/api/v1/sourcing/leads").status_code == 401


RUN_RESULT_HTML = """
<a class="link-to-detail" href="details/AA-11/?lang=de">
  <p class="beruf text-wrap">Steuerberaterin</p>
  <p class="akademische-grade text-wrap"></p>
  <p class="name text-wrap">Petra Fundstelle</p>
  <p class="address-display text-wrap">Fund &amp; Stelle StBG<br>Weg 1<br>70173 Stuttgart</p>
</a>
<a class="link-to-detail" href="details/BB-22/?lang=de">
  <p class="beruf text-wrap">Steuerberater</p>
  <p class="akademische-grade text-wrap"></p>
  <p class="name text-wrap">Hans Müller</p>
  <p class="address-display text-wrap">Weg 2<br>70173 Stuttgart</p>
</a>
"""


def test_sourcing_run_creates_leads_and_reports_counts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Bestehender Kandidat -> der zweite Verzeichnis-Treffer muss als
    # possible_duplicate markiert werden statt als frischer Lead.
    assert (
        client.post(
            "/api/v1/candidates", json={"first_name": "Hans", "last_name": "Mueller"}
        ).status_code
        == 201
    )
    monkeypatch.setattr(
        "cc_crm.services.steuerberater_verzeichnis.fetch_search_html",
        lambda plz_or_ort: RUN_RESULT_HTML,
    )

    response = client.post(
        "/api/v1/sourcing/run",
        json={"source_type": "steuerberaterverzeichnis", "plz_or_ort": ["70173"]},
    )
    assert response.status_code == 200
    result = response.json()
    assert result == {
        "found": 2,
        "created": 2,
        "skipped_existing": 0,
        "possible_duplicates": 1,
        "errors": [],
        "background_started": 0,
        "run_id": None,
    }

    # Wiederholter Lauf: gleiche Personen -> keine Doppel-Leads.
    second = client.post(
        "/api/v1/sourcing/run",
        json={"source_type": "steuerberaterverzeichnis", "plz_or_ort": ["70173"]},
    ).json()
    assert second["created"] == 0
    assert second["skipped_existing"] == 2

    leads = client.get("/api/v1/sourcing/leads").json()
    assert leads["total_count"] == 2
    by_name = {item["last_name"]: item for item in leads["items"]}
    assert by_name["Fundstelle"]["status"] == "pending"
    assert by_name["Fundstelle"]["current_employer"] == "Fund & Stelle StBG"
    assert by_name["Müller"]["status"] == "possible_duplicate"
    assert by_name["Müller"]["duplicate_of_candidate_id"] is not None
    assert by_name["Müller"]["raw_data"]["beruf"] == "Steuerberater"


def test_sourcing_run_reports_too_many_results_as_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "cc_crm.services.steuerberater_verzeichnis.fetch_search_html",
        lambda plz_or_ort: "<h5>Zu viele mögliche Treffer</h5>",
    )
    result = client.post(
        "/api/v1/sourcing/run",
        json={"source_type": "steuerberaterverzeichnis", "plz_or_ort": ["Berlin"]},
    ).json()
    assert result["found"] == 0
    assert result["created"] == 0
    assert len(result["errors"]) == 1
    assert "Berlin" in result["errors"][0]


def test_sourcing_run_wpk_source(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "cc_crm.services.wpk_berufsregister.fetch_search_results",
        lambda plz_or_ort: [
            {
                "istPerson": True,
                "klassifizierungBRO": "WP",
                "name": "Bechtold",
                "vorname": "Jürgen",
                "strasse": "Kronprinzstr. 8",
                "plz": "70173",
                "ort": "Stuttgart",
                "registernummer": 121669500,
                "statusTxt": "aktiv",
            },
            {"istPerson": False, "klassifizierungBRO": "WPG", "name": "X GmbH", "vorname": ""},
        ],
    )
    result = client.post(
        "/api/v1/sourcing/run",
        json={"source_type": "wpk_berufsregister", "plz_or_ort": ["70173"]},
    ).json()
    assert result["found"] == 1
    assert result["created"] == 1

    leads = client.get("/api/v1/sourcing/leads").json()
    lead = leads["items"][0]
    assert lead["source_type"] == "wpk_berufsregister"
    assert lead["last_name"] == "Bechtold"
    assert lead["raw_data"]["beruf"] == "Wirtschaftsprüfer/in"
    assert lead["raw_data"]["registernummer"] == 121669500


def test_sourcing_run_team_scrape_for_client_company(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    company = client.post(
        "/api/v1/clients",
        json={
            "name": "Muster & Partner StBG",
            "website": "https://kanzlei-muster.example",
            "postal_code": "50667",
            "city": "Köln",
        },
    ).json()

    pages = {
        "https://kanzlei-muster.example": '<a href="/team/">Unser Team</a>',
        "https://kanzlei-muster.example/team/": "<p>Dr. Eva Muster, Steuerberaterin</p>",
    }
    monkeypatch.setattr("cc_crm.services.kanzlei_team_scrape.fetch_page", lambda url: pages[url])
    monkeypatch.setattr(
        "cc_crm.services.kanzlei_team_scrape.generate_text",
        lambda **kwargs: (
            '[{"first_name": "Eva", "last_name": "Muster", "title": "Dr., Steuerberaterin"}]'
        ),
    )
    monkeypatch.setattr("cc_crm.services.sourcing.time.sleep", lambda seconds: None)

    result = client.post(
        "/api/v1/sourcing/run",
        json={"source_type": "kanzlei_team_page", "client_company_ids": [company["id"]]},
    ).json()
    assert result == {
        "found": 1,
        "created": 1,
        "skipped_existing": 0,
        "possible_duplicates": 0,
        "errors": [],
        "background_started": 0,
        "run_id": None,
    }

    lead = client.get("/api/v1/sourcing/leads").json()["items"][0]
    assert lead["source_type"] == "kanzlei_team_page"
    assert lead["current_employer"] == "Muster & Partner StBG"
    assert lead["matched_client_company_id"] == company["id"]
    assert lead["source_url"] == "https://kanzlei-muster.example/team/"
    assert lead["raw_data"]["title"] == "Dr., Steuerberaterin"
    assert (lead["postal_code"], lead["city"]) == ("50667", "Köln")


def test_sourcing_run_team_scrape_without_website_reports_error(
    client: TestClient,
) -> None:
    company = client.post("/api/v1/clients", json={"name": "Kanzlei ohne Web"}).json()
    result = client.post(
        "/api/v1/sourcing/run",
        json={"source_type": "kanzlei_team_page", "client_company_ids": [company["id"]]},
    ).json()
    assert result["created"] == 0
    assert "keine Website" in result["errors"][0]


def test_sourcing_run_rejects_brak_source(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sourcing/run",
        json={"source_type": "brak_anwaltsverzeichnis", "plz_or_ort": ["70173"]},
    )
    assert response.status_code == 422
