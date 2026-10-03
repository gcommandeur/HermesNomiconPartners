"""API der Outreach-Sequenzen: Verwaltung (nur Admin), Einschreibung, Stopp."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tests.api.test_team_lead import Person, _make_user

STEPS = [
    {"day_offset": 0, "channel": "email", "subject": "Hallo {first_name}", "body_template": "Hi"},
    {"day_offset": 3, "channel": "linkedin", "subject": "LinkedIn an {full_name}"},
]


def _admin(session_factory: sessionmaker[Session]) -> Person:
    return _make_user(session_factory, "admin@seq.example", "admin", "Admin")


def _candidate(client: TestClient, **overrides: object) -> dict:
    payload = {
        "first_name": "Anna",
        "last_name": "Muster",
        "email": "anna@example.com",
        "consent_received": True,
        **overrides,
    }
    response = client.post("/api/v1/candidates", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_sequence(client: TestClient, admin: Person, **overrides: object) -> dict:
    body = {"name": "Kaltakquise", "steps": STEPS, **overrides}
    response = client.post("/api/v1/sequences", json=body, headers=admin.headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_only_admin_manages_sequences(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _admin(session_factory)
    denied = client.post("/api/v1/sequences", json={"name": "X", "steps": STEPS})
    assert denied.status_code == 403
    sequence = _create_sequence(client, admin)
    assert [s["step_index"] for s in sequence["steps"]] == [0, 1]
    assert client.patch(
        f"/api/v1/sequences/{sequence['id']}", json={"is_active": False}
    ).status_code == 403

    updated = client.patch(
        f"/api/v1/sequences/{sequence['id']}",
        json={"name": "Neu", "steps": [STEPS[1]]},
        headers=admin.headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Neu"
    assert len(updated.json()["steps"]) == 1


def test_inactive_sequences_are_only_listed_for_admins(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _admin(session_factory)
    _create_sequence(client, admin, name="Aktiv")
    _create_sequence(client, admin, name="Inaktiv", is_active=False)
    member_view = client.get("/api/v1/sequences?include_inactive=true").json()
    assert [s["name"] for s in member_view] == ["Aktiv"]
    admin_view = client.get("/api/v1/sequences?include_inactive=true", headers=admin.headers)
    assert sorted(s["name"] for s in admin_view.json()) == ["Aktiv", "Inaktiv"]


def test_step_validation(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    admin = _admin(session_factory)

    def post(steps: list[dict], name: str = "V") -> int:
        return client.post(
            "/api/v1/sequences", json={"name": name, "steps": steps}, headers=admin.headers
        ).status_code

    assert post([]) == 422  # mindestens ein Schritt
    assert post([{"day_offset": 0, "channel": "email", "subject": "S"}]) == 422  # Mail ohne Text
    assert post([{"day_offset": 0, "channel": "fax", "subject": "S"}]) == 422  # Kanal
    assert post([{"day_offset": -1, "channel": "phone", "subject": "S"}]) == 422
    assert post([STEPS[1], STEPS[0]]) == 422  # nicht aufsteigend
    assert post(
        [{"day_offset": 0, "channel": "email", "subject": "{unbekannt}", "body_template": "x"}]
    ) == 422
    assert post(STEPS) == 201


def test_enroll_list_and_duplicate_rules(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _admin(session_factory)
    sequence = _create_sequence(client, admin)
    candidate = _candidate(client)
    me = client.get("/api/v1/auth/me").json()

    created = client.post(
        "/api/v1/sequence-enrollments",
        json={"sequence_id": sequence["id"], "candidate_id": candidate["id"]},
    )
    assert created.status_code == 201, created.text
    data = created.json()
    assert (data["status"], data["current_step_index"], data["total_steps"]) == ("active", 0, 2)
    assert data["owner_user_id"] == me["id"]
    assert data["next_step_channel"] == "email"
    assert data["next_step_due_on"] is not None

    duplicate = client.post(
        "/api/v1/sequence-enrollments",
        json={"sequence_id": sequence["id"], "candidate_id": candidate["id"]},
    )
    assert duplicate.status_code == 409

    listed = client.get(f"/api/v1/candidates/{candidate['id']}/sequence-enrollments").json()
    assert [item["id"] for item in listed] == [data["id"]]
    assert listed[0]["sequence_name"] == "Kaltakquise"

    # nach dem Stopp ist eine erneute Einschreibung erlaubt
    stopped = client.post(f"/api/v1/sequence-enrollments/{data['id']}/stop")
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["status"] == "stopped"
    assert stopped.json()["next_step_channel"] is None
    again = client.post(
        "/api/v1/sequence-enrollments",
        json={"sequence_id": sequence["id"], "candidate_id": candidate["id"]},
    )
    assert again.status_code == 201
    assert client.post(f"/api/v1/sequence-enrollments/{data['id']}/stop").status_code == 422


def test_enroll_rejects_unsuitable_candidates_and_inactive_sequences(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _admin(session_factory)
    sequence = _create_sequence(client, admin)
    inactive = _create_sequence(client, admin, name="Aus", is_active=False)
    no_mail = _candidate(client, first_name="Ohne", email=None)
    no_consent = _candidate(
        client, first_name="Keine", email="k@example.com", consent_received=False
    )
    ok = _candidate(client, first_name="Gut", email="g@example.com")

    def enroll(seq: dict, cand: dict) -> int:
        return client.post(
            "/api/v1/sequence-enrollments",
            json={"sequence_id": seq["id"], "candidate_id": cand["id"]},
        ).status_code

    assert enroll(sequence, no_mail) == 422
    assert enroll(sequence, no_consent) == 422
    assert enroll(inactive, ok) == 422
    assert enroll(sequence, ok) == 201


def test_only_owner_or_admin_can_stop(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _admin(session_factory)
    other = _make_user(session_factory, "other@seq.example", "member", "Other")
    sequence = _create_sequence(client, admin)
    candidate = _candidate(client)
    enrollment = client.post(
        "/api/v1/sequence-enrollments",
        json={"sequence_id": sequence["id"], "candidate_id": candidate["id"]},
    ).json()
    url = f"/api/v1/sequence-enrollments/{enrollment['id']}/stop"
    assert client.post(url, headers=other.headers).status_code == 403
    assert client.post(url, headers=admin.headers).status_code == 200
