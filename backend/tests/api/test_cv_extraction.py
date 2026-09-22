import json
from io import BytesIO

import docx
import pytest
from fastapi.testclient import TestClient

from cc_crm.services import cv_extraction

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx_bytes(text: str) -> bytes:
    # .doc wird nicht mehr angenommen (siehe api/v1/operational.py) - diese
    # Tests brauchen einen erlaubten Container mit lesbarem Text.
    document = docx.Document()
    document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _create_candidate(client: TestClient, **overrides: object) -> str:
    payload = {
        "candidate_number": "9001",
        "first_name": "Test",
        "last_name": "Kandidat",
    }
    payload.update(overrides)
    response = client.post("/api/v1/candidates", json=payload)
    assert response.status_code == 201
    return str(response.json()["id"])


def _upload_document(client: TestClient, candidate_id: str, content: bytes, filename: str) -> str:
    response = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "cv"},
        files={"file": (filename, content, _DOCX_MIME)},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


@pytest.fixture(autouse=True)
def _mock_generate_text(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_generate_text(
        *, system_prompt: str, user_message: str, max_tokens: int = 1000, timeout: float = 45.0
    ) -> str:
        return json.dumps(
            {
                "first_name": "Erika",
                "last_name": "Musterfrau",
                "email": "erika.musterfrau@example.com",
                "postal_code": "60327",
                "city": "Frankfurt am Main",
                "phone": "069 1234567",
                "job_title": "Steuerberater",
                "qualification": "Steuerberaterexamen",
                "ausbildung_titel": "Diplom-Kaufmann",
                "fachliche_schwerpunkte": ["Umsatzsteuer", "Konzernsteuerrecht"],
            }
        )

    monkeypatch.setattr(cv_extraction, "generate_text", fake_generate_text)


def test_cv_extraction_fills_only_empty_fields(client: TestClient) -> None:
    candidate_id = _create_candidate(client, city="Bereits gesetzt")
    document_id = _upload_document(
        client, candidate_id, _docx_bytes("Lebenslauf Test Kandidat..."), "cv.docx"
    )

    response = client.post(
        f"/api/v1/candidates/{candidate_id}/cv-extraction",
        json={"document_id": document_id},
    )
    assert response.status_code == 200
    suggestion = response.json()

    # first_name/last_name bereits gesetzt ("Test"/"Kandidat"), werden nicht ueberschrieben.
    assert suggestion["first_name"] is None
    assert suggestion["last_name"] is None
    assert suggestion["email"] == "erika.musterfrau@example.com"
    assert suggestion["postal_code"] == "60327"
    assert suggestion["city"] is None  # bereits gesetzt, wird nicht ueberschrieben
    assert suggestion["job_title"] == "Steuerberater"
    assert suggestion["fachliche_schwerpunkte"] == ["Umsatzsteuer", "Konzernsteuerrecht"]
    assert suggestion["source_is_agency_profile"] is False

    # Regressionsschutz: die erkannten Felder muessen sofort am Kandidaten
    # gespeichert sein, keine manuelle Bestaetigung mehr noetig (siehe
    # CandidateService.auto_fill_from_cv).
    candidate = client.get(f"/api/v1/candidates/{candidate_id}").json()
    assert candidate["first_name"] == "Test"
    assert candidate["email"] == "erika.musterfrau@example.com"
    assert candidate["postal_code"] == "60327"
    assert candidate["city"] == "Bereits gesetzt"
    assert candidate["job_title"] == "Steuerberater"
    assert candidate["fachliche_schwerpunkte"] == ["Umsatzsteuer", "Konzernsteuerrecht"]


def test_cv_extraction_does_not_overwrite_existing_fachliche_schwerpunkte(
    client: TestClient,
) -> None:
    candidate_id = _create_candidate(client, fachliche_schwerpunkte=["Bereits vorhanden"])
    document_id = _upload_document(
        client, candidate_id, _docx_bytes("Lebenslauf Test Kandidat..."), "cv.docx"
    )

    response = client.post(
        f"/api/v1/candidates/{candidate_id}/cv-extraction",
        json={"document_id": document_id},
    )
    assert response.status_code == 200
    suggestion = response.json()
    assert suggestion["fachliche_schwerpunkte"] is None

    candidate = client.get(f"/api/v1/candidates/{candidate_id}").json()
    assert candidate["fachliche_schwerpunkte"] == ["Bereits vorhanden"]


def test_cv_preview_returns_extracted_fields_without_a_candidate(client: TestClient) -> None:
    # Anlegen-Formular: der Kandidat existiert zu diesem Zeitpunkt noch
    # nicht, das Endpoint braucht daher keine candidate_id.
    response = client.post(
        "/api/v1/candidates/cv-preview",
        files={"file": ("cv.docx", _docx_bytes("Lebenslauf Test Kandidat..."), _DOCX_MIME)},
    )
    assert response.status_code == 200
    suggestion = response.json()

    assert suggestion["first_name"] == "Erika"
    assert suggestion["last_name"] == "Musterfrau"
    assert suggestion["email"] == "erika.musterfrau@example.com"
    assert suggestion["postal_code"] == "60327"
    assert suggestion["city"] == "Frankfurt am Main"
    assert suggestion["job_title"] == "Steuerberater"
    assert suggestion["fachliche_schwerpunkte"] == ["Umsatzsteuer", "Konzernsteuerrecht"]
    assert suggestion["source_is_agency_profile"] is False


def test_cv_preview_rejects_disallowed_file_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/candidates/cv-preview",
        files={"file": ("cv.txt", b"Lebenslauf", "text/plain")},
    )
    assert response.status_code == 415


def test_cv_preview_suppresses_name_and_contact_for_agency_letterhead(client: TestClient) -> None:
    # Anders als beim Kandidaten-gebundenen Endpoint gibt es hier noch keinen
    # vorhandenen Namen, der die Unterdrueckung "zufaellig" mit abdecken
    # wuerde - dieser Test prueft die Briefkopf-Erkennung daher gezielt fuer
    # first_name/last_name/email am neuen /cv-preview-Endpoint.
    letterhead = "Commandeur Consulting GmbH, Talstraße 112, 41199 Mönchengladbach"
    content = _docx_bytes(f"{letterhead}\n\nKandidatenprofil...")
    response = client.post(
        "/api/v1/candidates/cv-preview",
        files={"file": ("profil.docx", content, _DOCX_MIME)},
    )
    assert response.status_code == 200
    suggestion = response.json()

    assert suggestion["source_is_agency_profile"] is True
    assert suggestion["first_name"] is None
    assert suggestion["last_name"] is None
    assert suggestion["email"] is None
    assert suggestion["postal_code"] is None
    assert suggestion["job_title"] == "Steuerberater"


def test_cv_extraction_suppresses_address_for_agency_letterhead(client: TestClient) -> None:
    candidate_id = _create_candidate(client)
    letterhead = "Commandeur Consulting GmbH, Talstraße 112, 41199 Mönchengladbach"
    document_id = _upload_document(
        client, candidate_id, _docx_bytes(f"{letterhead}\n\nKandidatenprofil..."), "profil.docx"
    )

    response = client.post(
        f"/api/v1/candidates/{candidate_id}/cv-extraction",
        json={"document_id": document_id},
    )
    assert response.status_code == 200
    suggestion = response.json()

    assert suggestion["source_is_agency_profile"] is True
    assert suggestion["first_name"] is None
    assert suggestion["last_name"] is None
    assert suggestion["email"] is None
    assert suggestion["postal_code"] is None
    assert suggestion["city"] is None
    assert suggestion["phone"] is None
    assert suggestion["job_title"] == "Steuerberater"
