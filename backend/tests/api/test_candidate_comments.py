"""Autor-attributierte Kandidaten-Timeline (Task Teil B): Notizen und Feedback
tragen ihren Urheber, Interview/Offer/Placement-Ereignisse im AuditLog
ebenfalls, und GET /candidates/{id}/comments liefert beides fuer alle Nutzer
- auch Feedback an Prozessen von Kollegen."""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.note import Note
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService

COLLEAGUE_EMAIL = "kollege@commandeur.example"


@pytest.fixture
def colleague_headers(session_factory: sessionmaker[Session]) -> dict[str, str]:
    with session_factory() as session:
        session.add(
            User(
                email=COLLEAGUE_EMAIL,
                hashed_password=hash_password("x"),
                display_name="Karla Kollegin",
            )
        )
        session.commit()
        _, token = AuthService(session).login(COLLEAGUE_EMAIL, "x")
    return {"Authorization": f"Bearer {token}"}


def _candidate(client: TestClient, headers: dict[str, str] | None = None) -> dict:
    return client.post(
        "/api/v1/candidates",
        json={"first_name": "Tina", "last_name": "Timeline"},
        headers=headers or {},
    ).json()


def _feedback_payload(text: str = "Gutes Gespraech", **extra: object) -> dict:
    return {
        "feedback_type": "internal",
        "feedback_text": text,
        "received_at": "2026-10-01T09:00:00",
        **extra,
    }


def test_note_stores_author_and_returns_name(client: TestClient) -> None:
    me = client.get("/api/v1/auth/me").json()
    candidate = _candidate(client)

    created = client.post(
        "/api/v1/notes", json={"candidate_id": candidate["id"], "body": "Erster Eindruck"}
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["created_by_user_id"] == me["id"]
    assert body["created_by_name"] == (me.get("display_name") or me["email"])
    listed = client.get(f"/api/v1/notes?candidate_id={candidate['id']}").json()
    assert [item["created_by_name"] for item in listed] == [body["created_by_name"]]


def test_note_author_cannot_be_forged_via_payload(
    client: TestClient, colleague_headers: dict[str, str]
) -> None:
    me = client.get("/api/v1/auth/me").json()
    colleague = client.get("/api/v1/auth/me", headers=colleague_headers).json()
    candidate = _candidate(client)

    created = client.post(
        "/api/v1/notes",
        json={
            "candidate_id": candidate["id"],
            "body": "Gefaelscht?",
            "created_by_user_id": colleague["id"],
        },
    ).json()

    assert created["created_by_user_id"] == me["id"]


def test_legacy_note_without_author_does_not_break(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    candidate = _candidate(client)
    with session_factory() as session:
        session.add(Note(candidate_id=uuid.UUID(candidate["id"]), body="Alt-Notiz"))
        session.commit()

    listed = client.get(f"/api/v1/notes?candidate_id={candidate['id']}").json()
    assert listed[0]["created_by_user_id"] is None
    assert listed[0]["created_by_name"] is None
    comments = client.get(f"/api/v1/candidates/{candidate['id']}/comments").json()
    assert comments[0]["author"] is None


def test_feedback_author_is_set_server_side_and_not_forgeable(client: TestClient) -> None:
    me = client.get("/api/v1/auth/me").json()
    candidate = _candidate(client)
    submission = client.post("/api/v1/submissions", json={"candidate_id": candidate["id"]}).json()

    created = client.post(
        f"/api/v1/submissions/{submission['id']}/feedback",
        json=_feedback_payload(created_by="Jemand Anderes"),
    )

    assert created.status_code == 201, created.text
    assert created.json()["feedback"]["created_by"] == me["email"]


def test_quick_log_feedback_carries_author(client: TestClient) -> None:
    me = client.get("/api/v1/auth/me").json()
    candidate = _candidate(client)

    result = client.post(
        f"/api/v1/candidates/{candidate['id']}/quick-log",
        json={
            "stage": "qualification_call",
            "feedback_type": "internal",
            "feedback_text": "Quali-Call",
            "received_at": "2026-10-01T09:00:00",
        },
    ).json()

    assert result["feedback"]["created_by"] == me["email"]


def test_process_events_in_history_carry_the_author(client: TestClient) -> None:
    me = client.get("/api/v1/auth/me").json()
    candidate = _candidate(client)
    company = client.post("/api/v1/clients", json={"name": "Kanzlei Autor"}).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    sid = submission["id"]

    def move(status: str) -> None:
        response = client.patch(f"/api/v1/submissions/{sid}/transition", json={"status": status})
        assert response.status_code == 200, response.text

    for status in ("cv_in", "cv_out", "interview"):
        move(status)
    client.post(
        f"/api/v1/submissions/{sid}/interviews",
        json={"scheduled_at": "2026-10-20T10:00:00", "interview_type": "Erstgespraech"},
    )
    client.post(f"/api/v1/submissions/{sid}/feedback", json=_feedback_payload())
    move("offer")
    client.post(f"/api/v1/submissions/{sid}/offers", json={"offered_salary": "70000"})
    move("placement")
    placement = client.post(
        f"/api/v1/submissions/{sid}/placement",
        json={
            "start_date": date.today().isoformat(),
            "final_salary": "70000",
            "fee_percentage": "27",
        },
    ).json()
    client.post(f"/api/v1/placements/{placement['id']}/fees", json={"amount_net": "18900"})

    history = client.get(f"/api/v1/candidates/{candidate['id']}/history").json()
    by_action = {entry["action"]: entry for entry in history}
    for action in (
        "status_changed",
        "interview_scheduled",
        "feedback_received",
        "offer_received",
        "placement_created",
        "fee_calculated",
    ):
        assert action in by_action, action
        assert by_action[action]["changed_by"] == me["email"], action


def test_comments_endpoint_lists_notes_and_feedback_with_authors_for_everyone(
    client: TestClient, colleague_headers: dict[str, str]
) -> None:
    """Die Kollegin legt Prozess + Feedback + Notizen an; der Standard-Nutzer
    (kein Eigentuemer, kein Admin) sieht den Prozess selbst nicht (404), die
    Kommentare daran aber schon."""
    me = client.get("/api/v1/auth/me").json()
    candidate = _candidate(client)
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"]},
        headers=colleague_headers,
    ).json()
    sid = submission["id"]
    client.post(
        f"/api/v1/submissions/{sid}/feedback",
        json=_feedback_payload("Feedback der Kollegin"),
        headers=colleague_headers,
    )
    client.post(
        "/api/v1/notes",
        json={"candidate_id": candidate["id"], "body": "Allgemeine Notiz der Kollegin"},
        headers=colleague_headers,
    )
    client.post(
        "/api/v1/notes",
        json={"candidate_submission_id": sid, "body": "Prozess-Notiz der Kollegin"},
        headers=colleague_headers,
    )
    client.post("/api/v1/notes", json={"candidate_id": candidate["id"], "body": "Meine Notiz"})

    assert client.get(f"/api/v1/submissions/{sid}/feedback").status_code == 404

    comments = client.get(f"/api/v1/candidates/{candidate['id']}/comments")
    assert comments.status_code == 200, comments.text
    by_text = {item["text"]: item for item in comments.json()}
    assert set(by_text) == {
        "Feedback der Kollegin",
        "Allgemeine Notiz der Kollegin",
        "Prozess-Notiz der Kollegin",
        "Meine Notiz",
    }
    assert by_text["Feedback der Kollegin"]["kind"] == "feedback"
    assert by_text["Feedback der Kollegin"]["author"] == "Karla Kollegin"
    assert by_text["Allgemeine Notiz der Kollegin"]["author"] == "Karla Kollegin"
    assert by_text["Prozess-Notiz der Kollegin"]["author"] == "Karla Kollegin"
    assert by_text["Meine Notiz"]["author"] == (me.get("display_name") or me["email"])


def test_comments_endpoint_unknown_candidate_is_404(client: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/candidates/{missing}/comments").status_code == 404
