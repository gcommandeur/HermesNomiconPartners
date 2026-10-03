"""/candidates/cv-preview: gescannte PDFs laufen als Hintergrundjob (sofort
status="processing", Ergebnis per GET /cv-preview/{job_id}), alles andere
inline wie bisher. Plus: .doc wird im Upload klar abgelehnt.

Die Auswertung laeuft als Job der Warteschlange; die Tests arbeiten ihn mit
drain_jobs() ab (in der App macht das der Worker)."""

import json
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.errors import AIProviderError
from cc_crm.core.security import hash_password
from cc_crm.infrastructure.database import session as db_session_module
from cc_crm.models.cv_extraction_job import CvExtractionJob
from cc_crm.models.enums import CvExtractionJobStatus
from cc_crm.models.user import User
from cc_crm.services import cv_extraction, cv_extraction_jobs
from cc_crm.services.auth import AuthService
from tests.cv_document_fixtures import (
    DOC_OLE2_MAGIC,
    LONG_CV_TEXT,
    make_jpg,
    make_scanned_pdf,
    make_text_pdf,
)
from tests.jobs import drain_jobs

_DOC_MIME = "application/msword"


@pytest.fixture(autouse=True)
def _wire(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> Generator[dict[str, int], None, None]:
    # Der Hintergrundjob oeffnet seine eigene Session ueber SessionLocal -
    # im Test auf die In-Memory-DB zeigen lassen.
    monkeypatch.setattr(db_session_module, "SessionLocal", session_factory)
    counters = {"text": 0, "vision": 0}

    def fake_generate_text(**_: Any) -> str:
        counters["text"] += 1
        return json.dumps({"first_name": "Text", "last_name": "Pfad", "job_title": "StB"})

    def fake_generate_text_with_images(**_: Any) -> str:
        counters["vision"] += 1
        return json.dumps(
            {"first_name": "Erika", "last_name": "Scan", "job_title": "Steuerfachangestellte"}
        )

    monkeypatch.setattr(cv_extraction, "generate_text", fake_generate_text)
    monkeypatch.setattr(cv_extraction, "generate_text_with_images", fake_generate_text_with_images)
    yield counters


def _post(client: TestClient, filename: str, content: bytes, mime: str) -> Any:
    return client.post("/api/v1/candidates/cv-preview", files={"file": (filename, content, mime)})


def test_scanned_pdf_returns_processing_immediately_then_result_can_be_fetched(
    client: TestClient, session_factory: sessionmaker[Session], _wire: dict[str, int]
) -> None:
    response = _post(client, "scan.pdf", make_scanned_pdf(5), "application/pdf")

    assert response.status_code == 200
    started = response.json()
    assert started["status"] == "processing"
    assert started["job_id"]
    assert started["first_name"] is None  # noch nichts ausgewertet zurueckgegeben

    assert client.get(f"/api/v1/candidates/cv-preview/{started['job_id']}").json()["status"] == (
        "processing"
    )
    drain_jobs(session_factory)
    result = client.get(f"/api/v1/candidates/cv-preview/{started['job_id']}")
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "done"
    assert body["first_name"] == "Erika"
    assert body["last_name"] == "Scan"
    assert body["job_title"] == "Steuerfachangestellte"
    # Gescannt -> ausschliesslich Vision, kein Text-Call.
    assert _wire == {"text": 0, "vision": 1}


def test_failed_background_extraction_reports_failed_with_reason(
    client: TestClient, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(**_: Any) -> str:
        raise AIProviderError("credit balance is too low")

    monkeypatch.setattr(cv_extraction, "generate_text_with_images", failing)

    started = _post(client, "scan.pdf", make_scanned_pdf(2), "application/pdf").json()
    drain_jobs(session_factory)
    body = client.get(f"/api/v1/candidates/cv-preview/{started['job_id']}").json()

    assert body["status"] == "failed"
    assert "credit balance" in body["error"]


def test_job_result_is_only_visible_to_its_creator(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    started = _post(client, "scan.pdf", make_scanned_pdf(2), "application/pdf").json()

    with session_factory() as session:
        session.add(
            User(email="other@commandeur.example", hashed_password=hash_password("pw123456"))
        )
        session.commit()
        _, other_token = AuthService(session).login("other@commandeur.example", "pw123456")

    foreign = client.get(
        f"/api/v1/candidates/cv-preview/{started['job_id']}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert foreign.status_code == 404


def test_stuck_processing_job_is_reported_as_failed_after_timeout(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        owner = session.query(User).filter_by(email="test@commandeur.example").one()
        job = cv_extraction_jobs.create_job(session, owner.id)
        job_id = job.id
        stale = cv_extraction_jobs._now() - cv_extraction_jobs.JOB_STALE_AFTER * 2
        session.query(CvExtractionJob).filter_by(id=job_id).update({"created_at": stale})
        session.commit()

    body = client.get(f"/api/v1/candidates/cv-preview/{job_id}").json()

    assert body["status"] == "failed"
    assert "zu lange" in body["error"]
    with session_factory() as session:
        stored = session.get(CvExtractionJob, job_id)
        assert stored is not None and stored.status is CvExtractionJobStatus.FAILED


def test_normal_text_pdf_is_extracted_inline_without_a_job(
    client: TestClient, _wire: dict[str, int]
) -> None:
    pdf = make_text_pdf([LONG_CV_TEXT, LONG_CV_TEXT])

    response = _post(client, "cv.pdf", pdf, "application/pdf")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["job_id"] is None
    assert body["first_name"] == "Text"
    assert _wire["text"] == 1


def test_jpg_is_extracted_inline_via_vision(client: TestClient, _wire: dict[str, int]) -> None:
    response = _post(client, "foto.jpg", make_jpg(), "image/jpeg")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["first_name"] == "Erika"
    assert _wire == {"text": 0, "vision": 1}


def test_doc_upload_is_rejected_with_a_clear_message_on_cv_preview(client: TestClient) -> None:
    response = _post(client, "lebenslauf.doc", DOC_OLE2_MAGIC, _DOC_MIME)

    assert response.status_code == 415
    detail = response.json()["detail"]
    assert ".doc" in detail
    assert ".docx" in detail


def test_doc_upload_is_rejected_on_document_upload_too(client: TestClient) -> None:
    candidate = client.post(
        "/api/v1/candidates",
        json={"candidate_number": "9100", "first_name": "Doc", "last_name": "Test"},
    ).json()

    response = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate["id"], "document_type": "cv"},
        files={"file": ("lebenslauf.doc", DOC_OLE2_MAGIC, _DOC_MIME)},
    )

    assert response.status_code == 415
    assert ".docx" in response.json()["detail"]


def test_cv_preview_rejects_pdf_extension_with_forged_content(client: TestClient) -> None:
    """Punkt 3 des Auftrags "3 Mittel-Punkte umsetzen": derselbe Magic-
    Bytes-Check wie bei /documents/upload gilt auch fuer den zweiten
    Upload-Pfad (/candidates/cv-preview, siehe api/v1/candidates.py)."""
    response = _post(client, "cv.pdf", b"kein echtes PDF", "application/pdf")

    assert response.status_code == 400
