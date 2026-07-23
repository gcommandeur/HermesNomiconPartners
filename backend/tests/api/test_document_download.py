import pytest
from fastapi.testclient import TestClient

from cc_crm.api.v1 import operational


def _create_candidate(client: TestClient) -> str:
    payload = {"candidate_number": "9003", "first_name": "Test", "last_name": "Kandidat"}
    response = client.post("/api/v1/candidates", json=payload)
    assert response.status_code == 201
    return str(response.json()["id"])


def _upload_document(client: TestClient, candidate_id: str) -> str:
    response = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "cv"},
        files={"file": ("cv.pdf", b"%PDF-1.4 dummy content", "application/pdf")},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def test_download_returns_document_bytes(client: TestClient) -> None:
    candidate_id = _create_candidate(client)
    document_id = _upload_document(client, candidate_id)

    response = client.get(f"/api/v1/documents/{document_id}/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.4 dummy content"


def test_download_missing_file_returns_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate_id = _create_candidate(client)
    document_id = _upload_document(client, candidate_id)

    def _raise_not_found(storage_key: str) -> bytes:
        raise FileNotFoundError(storage_key)

    monkeypatch.setattr(operational, "read_document_bytes", _raise_not_found)

    response = client.get(f"/api/v1/documents/{document_id}/download")

    assert response.status_code == 404


def test_download_cloud_storage_unavailable_returns_503_not_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Der Dokumentenspeicher liegt im OneDrive-synchronisierten Ordner - eine
    dehydrierte Cloud-Platzhalterdatei (ReparsePoint) wirft beim Lesen einen
    OSError, keinen FileNotFoundError. Ohne diese Behandlung landete das als
    unbehandelter 500 "Internal Server Error" beim Nutzer (siehe Phase-1a-
    Bericht) statt einer klaren, temporären Fehlermeldung."""
    candidate_id = _create_candidate(client)
    document_id = _upload_document(client, candidate_id)

    def _raise_os_error(storage_key: str) -> bytes:
        raise OSError("[WinError 362] This file is currently not available for use.")

    monkeypatch.setattr(operational, "read_document_bytes", _raise_os_error)

    response = client.get(f"/api/v1/documents/{document_id}/download")

    assert response.status_code == 503
    assert "OneDrive" in response.json()["detail"]
