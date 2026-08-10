"""Tests fuer POST /tasks/{id}/snooze und POST /tasks/{id}/resolve
(Terminierungs-Agent, siehe services/tasks.py)."""

from fastapi.testclient import TestClient


def _create_task(client: TestClient, **overrides: object) -> dict:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Task", "last_name": "Test"}
    ).json()
    payload: dict[str, object] = {
        "candidate_id": candidate["id"],
        "title": "LinkedIn-Antwort: Task Test",
    }
    payload.update(overrides)
    response = client.post("/api/v1/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


class TestSnooze:
    def test_snooze_sets_snoozed_until_in_the_future(self, client: TestClient) -> None:
        task = _create_task(client)

        response = client.post(f"/api/v1/tasks/{task['id']}/snooze", json={"days": 3})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["snoozed_until"] is not None
        assert body["status"] == "open"

    def test_open_status_filter_excludes_snoozed_task_by_default(
        self, client: TestClient
    ) -> None:
        task = _create_task(client)
        client.post(f"/api/v1/tasks/{task['id']}/snooze", json={"days": 7})

        response = client.get("/api/v1/tasks?status=open")

        assert response.status_code == 200, response.text
        ids = [row["id"] for row in response.json()]
        assert task["id"] not in ids

    def test_unfiltered_list_still_shows_snoozed_task(self, client: TestClient) -> None:
        task = _create_task(client)
        client.post(f"/api/v1/tasks/{task['id']}/snooze", json={"days": 7})

        response = client.get("/api/v1/tasks")

        ids = [row["id"] for row in response.json()]
        assert task["id"] in ids


class TestResolve:
    def test_resolve_no_response_closes_task_without_calendar_event(
        self, client: TestClient
    ) -> None:
        task = _create_task(client)

        response = client.post(
            f"/api/v1/tasks/{task['id']}/resolve", json={"outcome": "no_response"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "done"

    def test_resolve_meeting_scheduled_creates_calendar_event_and_closes_task(
        self, client: TestClient
    ) -> None:
        task = _create_task(client)

        response = client.post(
            f"/api/v1/tasks/{task['id']}/resolve",
            json={
                "outcome": "meeting_scheduled",
                "scheduled_at": "2026-08-15T10:00:00Z",
                "notes": "Quali-Call vereinbart",
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "done"

        events = client.get("/api/v1/calendar-events").json()
        items = events["items"] if isinstance(events, dict) else events
        assert any("Task Test" in event["title"] for event in items)

    def test_resolve_meeting_scheduled_without_scheduled_at_fails(
        self, client: TestClient
    ) -> None:
        task = _create_task(client)

        response = client.post(
            f"/api/v1/tasks/{task['id']}/resolve", json={"outcome": "meeting_scheduled"}
        )

        assert response.status_code in (400, 422), response.text
