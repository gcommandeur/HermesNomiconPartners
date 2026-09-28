import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService


@pytest.fixture
def second_user_token(session_factory: sessionmaker[Session]) -> str:
    """Ein zweiter, normaler Nutzer (nicht der `client`-Fixture-Nutzer) - fuer
    die Sichtbarkeitstests (eigene vs. fremde Termine)."""
    with session_factory() as session:
        session.add(
            User(email="colleague@commandeurconsulting.de", hashed_password=hash_password("x"))
        )
        session.commit()
        _, token = AuthService(session).login("colleague@commandeurconsulting.de", "x")
        return token


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


def test_user_sees_only_own_events(
    client: TestClient, second_user_token: str
) -> None:
    own = client.post(
        "/api/v1/calendar-events",
        json={"title": "Eigenes Interview", "start_at": "2026-08-01T10:00:00"},
    ).json()
    other = client.post(
        "/api/v1/calendar-events",
        json={"title": "Fremder Termin", "start_at": "2026-08-01T11:00:00"},
        headers=auth_header(second_user_token),
    ).json()

    my_list = client.get("/api/v1/calendar-events").json()
    ids = [item["id"] for item in my_list]
    assert own["id"] in ids
    assert other["id"] not in ids


def test_user_cannot_access_or_modify_others_event(
    client: TestClient, second_user_token: str
) -> None:
    other = client.post(
        "/api/v1/calendar-events",
        json={"title": "Fremder Termin", "start_at": "2026-08-01T11:00:00"},
        headers=auth_header(second_user_token),
    ).json()

    get_response = client.get(f"/api/v1/calendar-events/{other['id']}")
    assert get_response.status_code == 403

    patch_response = client.patch(
        f"/api/v1/calendar-events/{other['id']}", json={"title": "Hijacked"}
    )
    assert patch_response.status_code == 403

    delete_response = client.delete(f"/api/v1/calendar-events/{other['id']}")
    assert delete_response.status_code == 403


def test_owner_can_update_and_delete_own_event(client: TestClient) -> None:
    event = client.post(
        "/api/v1/calendar-events",
        json={"title": "Quali Call", "start_at": "2026-08-02T09:00:00"},
    ).json()

    patched = client.patch(
        f"/api/v1/calendar-events/{event['id']}", json={"title": "Quali Call (verschoben)"}
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Quali Call (verschoben)"

    deleted = client.delete(f"/api/v1/calendar-events/{event['id']}")
    assert deleted.status_code == 204


def test_non_admin_owner_filter_is_ignored(client: TestClient, second_user_token: str) -> None:
    """Ein Standardnutzer, der versucht ueber owner_user_id die Termine eines
    anderen Nutzers zu sehen, bekommt weiterhin nur seine eigenen (Filter
    wird ignoriert, kein Fehler noetig, aber auch keine fremden Daten)."""
    other = client.post(
        "/api/v1/calendar-events",
        json={"title": "Fremder Termin", "start_at": "2026-08-01T11:00:00"},
        headers=auth_header(second_user_token),
    ).json()

    response = client.get(f"/api/v1/calendar-events?owner_user_id={other['owner_user_id']}")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert other["id"] not in ids


def test_admin_sees_all_events_and_can_filter_by_owner(
    client: TestClient, second_user_token: str, admin_token: str
) -> None:
    mine = client.post(
        "/api/v1/calendar-events",
        json={"title": "Mein Termin", "start_at": "2026-08-01T10:00:00"},
    ).json()
    other = client.post(
        "/api/v1/calendar-events",
        json={"title": "Kollegen-Termin", "start_at": "2026-08-01T11:00:00"},
        headers=auth_header(second_user_token),
    ).json()

    all_events = client.get("/api/v1/calendar-events", headers=auth_header(admin_token)).json()
    ids = [item["id"] for item in all_events]
    assert mine["id"] in ids
    assert other["id"] in ids

    filtered = client.get(
        f"/api/v1/calendar-events?owner_user_id={other['owner_user_id']}",
        headers=auth_header(admin_token),
    ).json()
    filtered_ids = [item["id"] for item in filtered]
    assert other["id"] in filtered_ids
    assert mine["id"] not in filtered_ids


def test_admin_can_create_event_for_another_user(
    client: TestClient, second_user_token: str, admin_token: str
) -> None:
    other_me = client.get("/api/v1/auth/me", headers=auth_header(second_user_token)).json()

    created = client.post(
        "/api/v1/calendar-events",
        json={
            "title": "Von Admin fuer Kollegen angelegt",
            "start_at": "2026-08-03T09:00:00",
            "owner_user_id": other_me["id"],
        },
        headers=auth_header(admin_token),
    ).json()
    assert created["owner_user_id"] == other_me["id"]

    # Der Kollege selbst sieht den Termin (er ist Owner)...
    colleague_list = client.get(
        "/api/v1/calendar-events", headers=auth_header(second_user_token)
    ).json()
    assert created["id"] in [item["id"] for item in colleague_list]


def test_missing_end_at_defaults_to_30_minutes_after_start(client: TestClient) -> None:
    created = client.post(
        "/api/v1/calendar-events",
        json={"title": "Kurzer Anruf", "start_at": "2026-09-28T10:00:00"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["end_at"] == "2026-09-28T10:30:00"


def test_end_at_before_minimum_duration_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/calendar-events",
        json={
            "title": "Zu kurzer Termin",
            "start_at": "2026-09-28T10:00:00",
            "end_at": "2026-09-28T10:10:00",
        },
    )
    assert response.status_code == 422, response.text
    assert "30 Minuten" in response.json()["detail"]


def test_end_at_before_start_at_is_rejected(client: TestClient) -> None:
    """Regressionstest fuer den Prod-Vorfall vom 2026-09-28 (Termin
    "Eric Bömicke"): end_at vor start_at wurde vom Graph-Push dauerhaft mit
    400 abgelehnt und liess den Sync fuer dieses Event stillschweigend
    scheitern - so etwas darf gar nicht erst gespeichert werden koennen."""
    response = client.post(
        "/api/v1/calendar-events",
        json={
            "title": "Vertauschte Zeiten",
            "start_at": "2026-09-28T10:00:00",
            "end_at": "2026-09-28T09:00:00",
        },
    )
    assert response.status_code == 422, response.text


def test_end_at_exactly_at_minimum_duration_is_accepted(client: TestClient) -> None:
    response = client.post(
        "/api/v1/calendar-events",
        json={
            "title": "Genau 30 Minuten",
            "start_at": "2026-09-28T10:00:00",
            "end_at": "2026-09-28T10:30:00",
        },
    )
    assert response.status_code == 201, response.text


def test_update_moving_only_start_at_is_checked_against_stored_end_at(
    client: TestClient,
) -> None:
    """Ein Update, das nur start_at aendert, darf die Mindestdauer-Pruefung
    nicht umgehen - sie muss gegen das bereits gespeicherte end_at laufen,
    nicht nur gegen die im Payload gesendeten Felder."""
    event = client.post(
        "/api/v1/calendar-events",
        json={
            "title": "Termin",
            "start_at": "2026-09-28T10:00:00",
            "end_at": "2026-09-28T10:30:00",
        },
    ).json()

    response = client.patch(
        f"/api/v1/calendar-events/{event['id']}",
        json={"start_at": "2026-09-28T10:25:00"},
    )
    assert response.status_code == 422, response.text
    assert "30 Minuten" in response.json()["detail"]


def test_update_moving_only_end_at_is_checked_against_stored_start_at(
    client: TestClient,
) -> None:
    event = client.post(
        "/api/v1/calendar-events",
        json={
            "title": "Termin",
            "start_at": "2026-09-28T10:00:00",
            "end_at": "2026-09-28T10:30:00",
        },
    ).json()

    response = client.patch(
        f"/api/v1/calendar-events/{event['id']}",
        json={"end_at": "2026-09-28T10:05:00"},
    )
    assert response.status_code == 422, response.text


def test_non_admin_cannot_set_owner_user_id(client: TestClient, second_user_token: str) -> None:
    """Ein Normalnutzer, der versucht per Body-Feld fuer einen anderen Nutzer
    anzulegen, wird serverseitig ignoriert - der Termin gehoert trotzdem ihm."""
    other_me = client.get("/api/v1/auth/me", headers=auth_header(second_user_token)).json()
    me = client.get("/api/v1/auth/me").json()

    created = client.post(
        "/api/v1/calendar-events",
        json={
            "title": "Versuch fuer anderen Nutzer",
            "start_at": "2026-08-03T09:00:00",
            "owner_user_id": other_me["id"],
        },
    ).json()
    assert created["owner_user_id"] == me["id"]
    assert created["owner_user_id"] != other_me["id"]
