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
    for target in ("qualification_call", "cv_in", "cv_out", "interview"):
        response = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition",
            json={"status": target},
        )
        assert response.status_code == 200, response.text
    return submission


def _create_interview(client: TestClient, submission_id: str) -> dict:
    response = client.post(
        f"/api/v1/submissions/{submission_id}/interviews",
        json={
            "scheduled_at": "2026-08-10T14:00:00",
            "interview_type": "video",
            "location_or_link": "https://example.com/meeting",
            "notes": "Erste Notiz",
        },
    )
    assert response.status_code == 201
    return response.json()


def _linked_event(client: TestClient, interview_id: str) -> dict | None:
    events = client.get("/api/v1/calendar-events").json()
    matching = [event for event in events if event["source_interview_id"] == interview_id]
    return matching[0] if matching else None


def test_update_interview_syncs_linked_calendar_event(client: TestClient) -> None:
    submission = _create_interview_ready_submission(client)
    interview = _create_interview(client, submission["id"])
    assert _linked_event(client, interview["id"]) is not None

    response = client.patch(
        f"/api/v1/submissions/{submission['id']}/interviews/{interview['id']}",
        json={
            "scheduled_at": "2026-08-12T16:30:00",
            "location_or_link": "https://example.com/new-room",
            "notes": "Verschoben",
        },
    )
    assert response.status_code == 200
    assert response.json()["scheduled_at"] == "2026-08-12T16:30:00"

    event = _linked_event(client, interview["id"])
    assert event is not None
    assert event["start_at"] == "2026-08-12T16:30:00"
    assert event["location"] == "https://example.com/new-room"
    assert event["notes"] == "Verschoben"


def test_update_interview_without_relevant_fields_does_not_touch_calendar_event(
    client: TestClient,
) -> None:
    """Nur scheduled_at/location_or_link/notes syncen den Kalendereintrag -
    eine Statusaenderung allein loest keinen Sync aus."""
    submission = _create_interview_ready_submission(client)
    interview = _create_interview(client, submission["id"])
    before = _linked_event(client, interview["id"])
    assert before is not None

    response = client.patch(
        f"/api/v1/submissions/{submission['id']}/interviews/{interview['id']}",
        json={"status": "completed"},
    )
    assert response.status_code == 200

    after = _linked_event(client, interview["id"])
    assert after is not None
    assert after["start_at"] == before["start_at"]


def test_update_interview_survives_calendar_sync_failure(client: TestClient) -> None:
    """Kalender-Sync-Fehler duerfen die eigentliche Interview-Aktion nicht
    verhindern (Nutzer-Vorgabe)."""
    submission = _create_interview_ready_submission(client)
    interview = _create_interview(client, submission["id"])

    with patch(
        "cc_crm.services.recruiting.RecruitingProcessService._sync_calendar_event_for_interview",
        side_effect=RuntimeError("simulated sync failure"),
    ):
        response = client.patch(
            f"/api/v1/submissions/{submission['id']}/interviews/{interview['id']}",
            json={"scheduled_at": "2026-08-13T10:00:00"},
        )

    assert response.status_code == 200
    assert response.json()["scheduled_at"] == "2026-08-13T10:00:00"

    # Session danach noch benutzbar.
    still_works = client.get(f"/api/v1/submissions/{submission['id']}/interviews")
    assert still_works.status_code == 200


def test_delete_interview_deletes_linked_calendar_event(client: TestClient) -> None:
    submission = _create_interview_ready_submission(client)
    interview = _create_interview(client, submission["id"])
    assert _linked_event(client, interview["id"]) is not None

    response = client.delete(
        f"/api/v1/submissions/{submission['id']}/interviews/{interview['id']}"
    )
    assert response.status_code == 204

    assert _linked_event(client, interview["id"]) is None
    remaining = client.get(f"/api/v1/submissions/{submission['id']}/interviews").json()
    assert remaining == []


def test_delete_interview_survives_calendar_event_deletion_failure(client: TestClient) -> None:
    submission = _create_interview_ready_submission(client)
    interview = _create_interview(client, submission["id"])

    with patch(
        "cc_crm.repositories.calendar_events.CalendarEventRepository.for_source_interview",
        side_effect=RuntimeError("simulated lookup failure"),
    ):
        response = client.delete(
            f"/api/v1/submissions/{submission['id']}/interviews/{interview['id']}"
        )

    assert response.status_code == 204
    remaining = client.get(f"/api/v1/submissions/{submission['id']}/interviews").json()
    assert remaining == []
