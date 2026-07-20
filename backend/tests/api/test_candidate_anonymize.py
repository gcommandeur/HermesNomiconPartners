import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService


@pytest.fixture
def admin_token(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        session.add(
            User(
                email="admin@commandeurconsulting.de",
                hashed_password=hash_password("x"),
                role="admin",
            )
        )
        session.commit()
        _, token = AuthService(session).login("admin@commandeurconsulting.de", "x")
        return token


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_candidate_with_pii(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/candidates",
        json={
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "email": "erika.musterfrau@example.com",
            "phone": "+49 170 1234567",
            "linkedin_url": "https://linkedin.com/in/erika-musterfrau",
            "referred_by": "Max Mustermann",
            "summary": "Persoenliche Zusammenfassung mit Namen.",
            "short_profile": "Kurzprofil mit Personenbezug.",
            "freitext_notizen": "Notiz ueber Erika persoenlich.",
            "wechselgrund": "Will naeher zu ihrer Familie ziehen.",
            "next_step": "Erika zurueckrufen.",
            "job_title": "Steuerberaterin",
            "postal_code": "10115",
            "city": "Berlin",
            "qualification": "Steuerberaterexamen",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_non_admin_cannot_anonymize_candidate(client: TestClient) -> None:
    candidate = _create_candidate_with_pii(client)
    response = client.post(f"/api/v1/candidates/{candidate['id']}/anonymize")
    assert response.status_code == 403


def test_admin_can_anonymize_candidate_pii_fields(
    client: TestClient, admin_token: str
) -> None:
    candidate = _create_candidate_with_pii(client)

    response = client.post(
        f"/api/v1/candidates/{candidate['id']}/anonymize", headers=auth_header(admin_token)
    )
    assert response.status_code == 200
    body = response.json()

    assert body["first_name"] == "Anonymisiert"
    assert body["last_name"] == "Anonymisiert"
    assert body["email"] is None
    assert body["phone"] is None
    assert body["linkedin_url"] is None
    assert body["referred_by"] is None
    assert body["summary"] is None
    assert body["short_profile"] is None
    assert body["freitext_notizen"] is None
    assert body["wechselgrund"] is None
    assert body["next_step"] is None
    assert body["consent_received"] is False
    assert body["cv_available"] is False


def test_anonymize_keeps_structured_statistical_fields(
    client: TestClient, admin_token: str
) -> None:
    candidate = _create_candidate_with_pii(client)

    response = client.post(
        f"/api/v1/candidates/{candidate['id']}/anonymize", headers=auth_header(admin_token)
    )
    body = response.json()

    assert body["job_title"] == "Steuerberaterin"
    assert body["postal_code"] == "10115"
    assert body["city"] == "Berlin"
    assert body["qualification"] == "Steuerberaterexamen"
    assert body["status"] == "active"
    assert body["candidate_number"] is None or isinstance(body["candidate_number"], str)


def test_anonymize_keeps_record_and_referential_integrity(
    client: TestClient, admin_token: str
) -> None:
    """Der Datensatz selbst und darauf verweisende Prozesse bleiben nach der
    Anonymisierung bestehen (Statistiken bleiben auswertbar)."""
    candidate = _create_candidate_with_pii(client)
    submission = client.post(
        "/api/v1/submissions", json={"candidate_id": candidate["id"]}
    ).json()

    client.post(
        f"/api/v1/candidates/{candidate['id']}/anonymize", headers=auth_header(admin_token)
    )

    still_there = client.get(f"/api/v1/candidates/{candidate['id']}")
    assert still_there.status_code == 200

    submission_still_there = client.get(f"/api/v1/submissions/{submission['id']}")
    assert submission_still_there.status_code == 200
    assert submission_still_there.json()["candidate_id"] == candidate["id"]


def test_anonymize_deletes_linked_documents(client: TestClient, admin_token: str) -> None:
    candidate = _create_candidate_with_pii(client)
    upload = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate["id"], "document_type": "cv"},
        files={"file": ("lebenslauf-erika-musterfrau.pdf", b"%PDF-1.4 dummy", "application/pdf")},
    )
    assert upload.status_code == 201

    client.post(
        f"/api/v1/candidates/{candidate['id']}/anonymize", headers=auth_header(admin_token)
    )

    documents = client.get(
        f"/api/v1/documents?owner_type=candidate&owner_id={candidate['id']}"
    ).json()
    assert documents == []


def test_anonymize_logs_audit_entry_without_pii(client: TestClient, admin_token: str) -> None:
    candidate = _create_candidate_with_pii(client)

    client.post(
        f"/api/v1/candidates/{candidate['id']}/anonymize", headers=auth_header(admin_token)
    )

    logs = client.get("/api/v1/audit-logs", headers=auth_header(admin_token)).json()
    matching = [
        entry
        for entry in logs
        if entry["entity_type"] == "candidate"
        and entry["action"] == "anonymized"
        and entry["entity_id"] == candidate["id"]
    ]
    assert len(matching) == 1
    entry = matching[0]
    assert entry["changed_by"] == "admin@commandeurconsulting.de"
    # Kein alter/neuer Wert darf personenbezogene Daten enthalten - das
    # Audit-Log darf nicht genau das reproduzieren, was gerade entfernt wurde.
    serialized = str(entry)
    assert "Erika" not in serialized
    assert "Musterfrau" not in serialized
    assert "erika.musterfrau@example.com" not in serialized
