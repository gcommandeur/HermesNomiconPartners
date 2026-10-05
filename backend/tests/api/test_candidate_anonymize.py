import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.candidate import Candidate
from cc_crm.models.recruiting import AuditLog
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


def _full_candidate(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/candidates",
        json={
            "first_name": "Greta",
            "last_name": "Vollstaendig",
            "email": "greta.vollstaendig@example.com",
            "phone": "+49 170 7654321",
            "job_title": "Steuerberaterin",
            "consent_received": True,
            "current_employer_internal": "Kanzlei Geheimarbeitgeber GmbH",
            "examensnoten": "Steuerberaterexamen 3,5 (Geheimnote)",
            "salary_expectation": "Gehalt 88.000 geheim",
            "notice_period": "Kuendigungsfrist 6 Monate geheim",
            "berufliche_stationen": [
                {"kanzleityp": "Wirtschaftspruefung", "kanzleigroesse": "gross", "dauer_jahre": 4}
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_anonymize_clears_second_stage_fields_and_keeps_consent_proof(
    client: TestClient, admin_token: str, session_factory: sessionmaker[Session]
) -> None:
    candidate = _full_candidate(client)
    # Vorbedingung: der Nachweis wurde beim Setzen der Einwilligung erfasst.
    assert candidate["consent_recorded_at"] is not None
    assert candidate["consent_source"] == "hermes_manuell"
    recorded_at = candidate["consent_recorded_at"]
    with session_factory() as session:
        row = session.get(Candidate, uuid.UUID(candidate["id"]))
        assert row is not None
        row.cv_extraction_raw = {"name": "Greta Vollstaendig", "arbeitgeber": "Geheimarbeitgeber"}
        session.commit()

    response = client.post(
        f"/api/v1/candidates/{candidate['id']}/anonymize", headers=auth_header(admin_token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current_employer_internal"] is None
    assert body["examensnoten"] is None
    assert body["salary_expectation"] is None
    assert body["notice_period"] is None
    assert body["berufliche_stationen"] == []
    # Einwilligung: Flag aus, Nachweis (Datum, Quelle, Pseudonym) bleibt, Zeitpunkt gesetzt.
    assert body["consent_received"] is False
    assert body["consent_recorded_at"].rstrip("Z") == recorded_at.rstrip("Z")
    assert body["consent_source"] == "hermes_manuell"
    assert body["anonymized_at"] is not None
    assert body["candidate_number"] == candidate["candidate_number"]
    assert body["email"] is None and body["phone"] is None

    with session_factory() as session:
        row = session.get(Candidate, uuid.UUID(candidate["id"]))
        assert row is not None
        assert row.cv_extraction_raw is None
        serialized = str(
            [(e.old_values, e.new_values) for e in session.scalars(select(AuditLog)).all()]
        )
    for secret in (
        "Greta",
        "Vollstaendig",
        "greta.vollstaendig@example.com",
        "Geheimarbeitgeber",
        "Geheimnote",
        "88.000",
    ):
        assert secret not in serialized, secret
    # Audit-Eintrag der Anonymisierung traegt den Einwilligungsnachweis ohne Personenbezug.
    logs = client.get("/api/v1/audit-logs", headers=auth_header(admin_token)).json()
    entry = next(
        e for e in logs if e["action"] == "anonymized" and e["entity_id"] == candidate["id"]
    )
    assert entry["new_values"]["consent_was_given"] is True
    assert entry["new_values"]["consent_recorded_at"] is not None
    assert "cv_extraction_raw" in entry["new_values"]["fields_cleared"]


def test_consent_recorded_when_flag_turns_true_and_never_overwritten(client: TestClient) -> None:
    created = client.post(
        "/api/v1/candidates", json={"first_name": "Cora", "last_name": "Spaeter"}
    ).json()
    assert created["consent_recorded_at"] is None

    first = client.patch(f"/api/v1/candidates/{created['id']}", json={"consent_received": True})
    assert first.status_code == 200, first.text
    stamp = first.json()["consent_recorded_at"]
    assert stamp is not None and first.json()["consent_source"] == "hermes_manuell"

    client.patch(f"/api/v1/candidates/{created['id']}", json={"consent_received": False})
    again = client.patch(f"/api/v1/candidates/{created['id']}", json={"consent_received": True})
    assert again.json()["consent_recorded_at"].rstrip("Z") == stamp.rstrip("Z")


def test_anonymize_without_recorded_consent_date_does_not_invent_one(
    client: TestClient, admin_token: str, session_factory: sessionmaker[Session]
) -> None:
    """Altbestand: Flag gesetzt, aber kein Datum erfasst -> Datum bleibt NULL."""
    candidate = _full_candidate(client)
    with session_factory() as session:
        row = session.get(Candidate, uuid.UUID(candidate["id"]))
        assert row is not None
        row.consent_recorded_at = None
        row.consent_source = None
        session.commit()
    body = client.post(
        f"/api/v1/candidates/{candidate['id']}/anonymize", headers=auth_header(admin_token)
    ).json()
    assert body["consent_recorded_at"] is None
    logs = client.get("/api/v1/audit-logs", headers=auth_header(admin_token)).json()
    entry = next(
        e for e in logs if e["action"] == "anonymized" and e["entity_id"] == candidate["id"]
    )
    assert entry["new_values"]["consent_was_given"] is True
    assert entry["new_values"]["consent_recorded_at"] is None
