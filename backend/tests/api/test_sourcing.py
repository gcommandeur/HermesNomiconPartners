"""Sourcing-Agent Phase 1: Review-Workflow (Lead anlegen, Duplikat-Abgleich
gegen bestehende Kandidaten, approve/reject)."""

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
