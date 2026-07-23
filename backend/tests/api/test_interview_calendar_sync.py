from unittest.mock import patch

from fastapi.testclient import TestClient


def _create_interview_ready_submission(client: TestClient) -> dict:
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Erika", "last_name": "Musterfrau"},
    ).json()
    company = client.post(
        "/api/v1/clients",
        json={"name": "PwC Deutschland", "status": "active"},
    ).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    for target in ("cv_in", "cv_out", "interview"):
        response = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition",
            json={"status": target},
        )
        assert response.status_code == 200, response.text
    return submission


def test_creating_interview_auto_creates_calendar_event(client: TestClient) -> None:
    submission = _create_interview_ready_submission(client)
    me = client.get("/api/v1/auth/me").json()

    interview = client.post(
        f"/api/v1/submissions/{submission['id']}/interviews",
        json={
            "scheduled_at": "2026-08-10T14:00:00",
            "interview_type": "video",
            "location_or_link": "https://example.com/meeting",
            "notes": "Bitte Unterlagen vorher pruefen.",
        },
    )
    assert interview.status_code == 201
    interview_id = interview.json()["id"]

    events = client.get("/api/v1/calendar-events").json()
    matching = [event for event in events if event["source_interview_id"] == interview_id]
    assert len(matching) == 1, f"expected exactly one linked calendar event, got {len(matching)}"

    event = matching[0]
    assert event["event_type"] == "interview"
    assert event["start_at"] == "2026-08-10T14:00:00"
    assert event["owner_user_id"] == me["id"]
    assert event["created_by_user_id"] == me["id"]
    assert event["candidate_submission_id"] == submission["id"]
    assert event["candidate_id"] == submission["candidate_id"]
    assert event["client_company_id"] == submission["client_company_id"]
    assert event["location"] == "https://example.com/meeting"
    assert event["notes"] == "Bitte Unterlagen vorher pruefen."
    assert event["reminder_minutes_before"] == 60
    assert "Erika Musterfrau" in event["title"]
    assert "PwC Deutschland" in event["title"]


def test_interview_creation_survives_calendar_event_failure(client: TestClient) -> None:
    """Die Interview-Erstellung ist die primaere Aktion - ein Fehler beim
    (begleitenden) Kalendereintrag darf sie nicht scheitern lassen."""
    submission = _create_interview_ready_submission(client)

    with patch(
        "cc_crm.services.recruiting.RecruitingProcessService._create_calendar_event_for_interview",
        side_effect=RuntimeError("simulated calendar failure"),
    ):
        response = client.post(
            f"/api/v1/submissions/{submission['id']}/interviews",
            json={
                "scheduled_at": "2026-08-11T09:00:00",
                "interview_type": "onsite",
            },
        )

    assert response.status_code == 201
    assert (
        client.get(f"/api/v1/submissions/{submission['id']}").json()["status"] == "interview"
    )

    # Und die Session ist danach noch benutzbar (kein hängender/kaputter State).
    follow_up_check = client.get(f"/api/v1/submissions/{submission['id']}/interviews")
    assert follow_up_check.status_code == 200
    assert len(follow_up_check.json()) == 1
