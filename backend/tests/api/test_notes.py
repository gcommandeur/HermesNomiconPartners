import time

from fastapi.testclient import TestClient


def _create_candidate(client: TestClient, candidate_number: str = "9101") -> str:
    payload = {"candidate_number": candidate_number, "first_name": "Test", "last_name": "Kandidat"}
    response = client.post("/api/v1/candidates", json=payload)
    assert response.status_code == 201
    return str(response.json()["id"])


def test_create_and_get_note(client: TestClient) -> None:
    candidate_id = _create_candidate(client)

    response = client.post(
        "/api/v1/notes", json={"candidate_id": candidate_id, "body": "Erste Notiz"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["body"] == "Erste Notiz"
    assert body["candidate_id"] == candidate_id
    assert body["candidate_submission_id"] is None


def test_list_notes_filtered_by_candidate_excludes_submission_bound_notes(
    client: TestClient,
) -> None:
    candidate_id = _create_candidate(client, "9102")
    company = client.post("/api/v1/clients", json={"name": "Kanzlei Notizen"}).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate_id, "client_company_id": company["id"]},
    ).json()

    general_note = client.post(
        "/api/v1/notes", json={"candidate_id": candidate_id, "body": "Allgemeine Notiz"}
    )
    assert general_note.status_code == 201
    submission_note = client.post(
        "/api/v1/notes",
        json={
            "candidate_id": candidate_id,
            "candidate_submission_id": submission["id"],
            "body": "Prozessgebundene Notiz",
        },
    )
    assert submission_note.status_code == 201

    general_response = client.get("/api/v1/notes", params={"candidate_id": candidate_id})
    assert general_response.status_code == 200
    general_bodies = [note["body"] for note in general_response.json()]
    assert general_bodies == ["Allgemeine Notiz"]

    submission_response = client.get(
        "/api/v1/notes", params={"submission_id": submission["id"]}
    )
    assert submission_response.status_code == 200
    submission_bodies = [note["body"] for note in submission_response.json()]
    assert submission_bodies == ["Prozessgebundene Notiz"]


def test_list_notes_ordered_by_created_at_descending(client: TestClient) -> None:
    candidate_id = _create_candidate(client, "9103")

    first = client.post("/api/v1/notes", json={"candidate_id": candidate_id, "body": "Zuerst"})
    assert first.status_code == 201
    # SQLites CURRENT_TIMESTAMP (server_default von TimestampMixin.created_at)
    # hat nur Sekundenaufloesung - ohne eine kleine Pause landen beide Notizen
    # sonst auf demselben created_at und die Sortierreihenfolge waere nicht
    # deterministisch (in Postgres/Produktion mit Mikrosekundenaufloesung
    # tritt das nicht auf).
    time.sleep(1.1)
    second = client.post("/api/v1/notes", json={"candidate_id": candidate_id, "body": "Danach"})
    assert second.status_code == 201

    response = client.get("/api/v1/notes", params={"candidate_id": candidate_id})

    assert response.status_code == 200
    bodies = [note["body"] for note in response.json()]
    assert bodies == ["Danach", "Zuerst"]


def test_update_and_delete_note(client: TestClient) -> None:
    candidate_id = _create_candidate(client, "9104")
    created = client.post("/api/v1/notes", json={"candidate_id": candidate_id, "body": "Original"})
    note_id = created.json()["id"]

    updated = client.patch(f"/api/v1/notes/{note_id}", json={"body": "Geaendert"})
    assert updated.status_code == 200
    assert updated.json()["body"] == "Geaendert"

    deleted = client.delete(f"/api/v1/notes/{note_id}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/notes/{note_id}")
    assert missing.status_code == 404
