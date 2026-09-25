"""API-Tests fuer die Loeschanfragen-Nachverfolgung (Art. 17 DSGVO,
Punkt 3 des Auftrags "5 Hoch-Punkte umsetzen"). Die eigentliche
Anonymisierungslogik (CandidateService.anonymize) ist bereits an anderer
Stelle getestet - hier geht es NUR um die Nachverfolgung drumherum."""

from datetime import datetime, timedelta

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


def _create_candidate(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/candidates", json={"first_name": "Anna", "last_name": "Muster"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_non_admin_cannot_list_or_create_deletion_requests(client: TestClient) -> None:
    candidate = _create_candidate(client)
    assert client.get("/api/v1/deletion-requests").status_code == 403
    assert (
        client.post(
            "/api/v1/deletion-requests",
            json={"candidate_id": candidate["id"], "requested_via": "email"},
        ).status_code
        == 403
    )


def test_create_sets_a_30_day_deadline_by_default(
    client: TestClient, admin_token: str
) -> None:
    candidate = _create_candidate(client)

    response = client.post(
        "/api/v1/deletion-requests",
        json={"candidate_id": candidate["id"], "requested_via": "telefon"},
        headers=auth_header(admin_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()

    requested_at = datetime.fromisoformat(body["requested_at"])
    deadline = datetime.fromisoformat(body["deadline"])
    assert deadline - requested_at == timedelta(days=30)
    assert body["completed_at"] is None
    assert body["candidate_first_name"] == "Anna"
    assert body["candidate_last_name"] == "Muster"


def test_list_open_sorted_by_deadline_ascending_excludes_completed(
    client: TestClient, admin_token: str
) -> None:
    candidate_a = _create_candidate(client)
    candidate_b = _create_candidate(client)
    candidate_c = _create_candidate(client)

    for candidate in (candidate_a, candidate_b, candidate_c):
        response = client.post(
            "/api/v1/deletion-requests",
            json={"candidate_id": candidate["id"], "requested_via": "email"},
            headers=auth_header(admin_token),
        )
        assert response.status_code == 200, response.text

    open_requests = client.get(
        "/api/v1/deletion-requests", headers=auth_header(admin_token)
    ).json()
    assert len(open_requests) == 3
    deadlines = [entry["deadline"] for entry in open_requests]
    assert deadlines == sorted(deadlines)

    # Eine erledigte Anfrage verschwindet aus der offenen Liste (default
    # open_only=true).
    complete_response = client.post(
        f"/api/v1/deletion-requests/{open_requests[0]['id']}/complete",
        headers=auth_header(admin_token),
    )
    assert complete_response.status_code == 200, complete_response.text

    still_open = client.get(
        "/api/v1/deletion-requests", headers=auth_header(admin_token)
    ).json()
    assert len(still_open) == 2

    everything = client.get(
        "/api/v1/deletion-requests?open_only=false", headers=auth_header(admin_token)
    ).json()
    assert len(everything) == 3


def test_complete_anonymizes_the_candidate_and_records_who_did_it(
    client: TestClient, admin_token: str
) -> None:
    """"Erledigen" verknuepft mit dem BESTEHENDEN, unveraenderten
    Anonymisieren-Endpunkt - der Kandidat ist danach anonymisiert, UND die
    Loeschanfrage trägt completed_at/completed_by_user_id."""
    candidate = _create_candidate(client)
    request = client.post(
        "/api/v1/deletion-requests",
        json={"candidate_id": candidate["id"], "requested_via": "email"},
        headers=auth_header(admin_token),
    ).json()

    response = client.post(
        f"/api/v1/deletion-requests/{request['id']}/complete",
        headers=auth_header(admin_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["completed_at"] is not None
    assert body["completed_by_user_id"] is not None

    anonymized_candidate = client.get(f"/api/v1/candidates/{candidate['id']}").json()
    assert anonymized_candidate["first_name"] == "Anonymisiert"


def test_complete_twice_is_rejected(client: TestClient, admin_token: str) -> None:
    candidate = _create_candidate(client)
    request = client.post(
        "/api/v1/deletion-requests",
        json={"candidate_id": candidate["id"], "requested_via": "email"},
        headers=auth_header(admin_token),
    ).json()

    first = client.post(
        f"/api/v1/deletion-requests/{request['id']}/complete",
        headers=auth_header(admin_token),
    )
    assert first.status_code == 200, first.text

    second = client.post(
        f"/api/v1/deletion-requests/{request['id']}/complete",
        headers=auth_header(admin_token),
    )
    assert second.status_code == 409
