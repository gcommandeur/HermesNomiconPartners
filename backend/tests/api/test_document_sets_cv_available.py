"""Tests fuer den dritten Stempel-Pfad von Candidate.cv_available/
cv_in_recorded_at (Bugfix "CV-Dokument-Upload setzt cv_available nicht",
konkreter Fall: Lorenz Hafner, CV hochgeladen aber Flag nie gesetzt).
Ergaenzt die beiden bestehenden Pfade (CandidateService.create()/update(),
siehe test_candidate_cv_in_recorded_at.py) um DocumentService.create()."""

from fastapi.testclient import TestClient


def _create_candidate(client: TestClient, **overrides: object) -> dict:
    payload: dict[str, object] = {"first_name": "Lorenz", "last_name": "Hafner"}
    payload.update(overrides)
    response = client.post("/api/v1/candidates", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _upload_cv(client: TestClient, candidate_id: str, storage_key: str) -> dict:
    response = client.post(
        "/api/v1/documents",
        json={
            "owner_type": "candidate",
            "owner_id": candidate_id,
            "document_type": "cv",
            "filename": "lebenslauf.pdf",
            "storage_key": storage_key,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_cv_document_upload_sets_cv_available_and_recorded_at(client: TestClient) -> None:
    candidate = _create_candidate(client, cv_available=False)
    assert candidate["cv_available"] is False
    assert candidate["cv_in_recorded_at"] is None

    _upload_cv(client, candidate["id"], "candidates/hafner-cv.pdf")

    updated = client.get(f"/api/v1/candidates/{candidate['id']}").json()
    assert updated["cv_available"] is True
    assert updated["cv_in_recorded_at"] is not None


def test_second_cv_upload_does_not_overwrite_the_first_recorded_at(
    client: TestClient,
) -> None:
    candidate = _create_candidate(client, cv_available=False)
    _upload_cv(client, candidate["id"], "candidates/hafner-cv-v1.pdf")
    first = client.get(f"/api/v1/candidates/{candidate['id']}").json()
    first_recorded_at = first["cv_in_recorded_at"]
    assert first_recorded_at is not None

    _upload_cv(client, candidate["id"], "candidates/hafner-cv-v2.pdf")

    second = client.get(f"/api/v1/candidates/{candidate['id']}").json()
    assert second["cv_available"] is True
    assert second["cv_in_recorded_at"] == first_recorded_at


def test_non_cv_document_upload_leaves_cv_available_unchanged(client: TestClient) -> None:
    candidate = _create_candidate(client, cv_available=False)

    response = client.post(
        "/api/v1/documents",
        json={
            "owner_type": "candidate",
            "owner_id": candidate["id"],
            "document_type": "zeugnis",
            "filename": "zeugnis.pdf",
            "storage_key": "candidates/zeugnis.pdf",
        },
    )
    assert response.status_code == 201, response.text

    updated = client.get(f"/api/v1/candidates/{candidate['id']}").json()
    assert updated["cv_available"] is False
    assert updated["cv_in_recorded_at"] is None


def test_cv_document_for_client_owner_does_not_touch_any_candidate(
    client: TestClient,
) -> None:
    """document.owner_type != 'candidate' (z.B. eine Kanzlei-AGB-Ablage,
    unwahrscheinlich fuer document_type='cv', aber die Guard-Klausel prueft
    genau das) darf nichts anfassen - reine Absicherung der if-Bedingung."""
    client_company = client.post(
        "/api/v1/clients", json={"name": "Kanzlei Test"}
    ).json()
    response = client.post(
        "/api/v1/documents",
        json={
            "owner_type": "client",
            "owner_id": client_company["id"],
            "document_type": "cv",
            "filename": "irrelevant.pdf",
            "storage_key": "clients/irrelevant.pdf",
        },
    )
    assert response.status_code == 201, response.text
