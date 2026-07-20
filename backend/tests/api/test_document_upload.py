from fastapi.testclient import TestClient

from cc_crm.core.config import get_settings


def _create_candidate(client: TestClient) -> str:
    payload = {"candidate_number": "9002", "first_name": "Test", "last_name": "Kandidat"}
    response = client.post("/api/v1/candidates", json=payload)
    assert response.status_code == 201
    return str(response.json()["id"])


def test_upload_rejects_disallowed_extension(client: TestClient) -> None:
    candidate_id = _create_candidate(client)

    response = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "cv"},
        files={"file": ("malware.exe", b"irrelevant", "application/octet-stream")},
    )

    assert response.status_code == 415
    assert "erlaubt" in response.json()["detail"].lower()


def test_upload_rejects_mismatched_content_type(client: TestClient) -> None:
    candidate_id = _create_candidate(client)

    response = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "cv"},
        files={"file": ("cv.pdf", b"irrelevant", "text/plain")},
    )

    assert response.status_code == 415


def test_upload_rejects_file_over_size_limit(client: TestClient) -> None:
    candidate_id = _create_candidate(client)
    max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
    oversized_content = b"a" * (max_bytes + 1)

    response = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "cv"},
        files={"file": ("cv.pdf", oversized_content, "application/pdf")},
    )

    assert response.status_code == 413
    assert (
        "groß" in response.json()["detail"].lower() or "gross" in response.json()["detail"].lower()
    )


def test_upload_accepts_normal_pdf(client: TestClient) -> None:
    candidate_id = _create_candidate(client)

    response = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "cv"},
        files={"file": ("cv.pdf", b"%PDF-1.4 dummy content", "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "cv.pdf"
    assert body["content_type"] == "application/pdf"
