"""Automatisch aus dem Prozessstatus erzeugte Follow-up-Tasks muessen bei
jedem weiteren Statuswechsel geschlossen werden (siehe services/
submissions.py::AUTO_FOLLOW_UP_DESCRIPTION) - vorher blieb z.B. "CV-Out
nachfassen" offen, obwohl der Prozess laengst bei "Interview" war."""

from fastapi.testclient import TestClient


def _create_submission_at_cv_out(client: TestClient) -> dict:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Follow", "last_name": "Up"}
    ).json()
    company = client.post("/api/v1/clients", json={"name": "Kanzlei FollowUp"}).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    for target in ("cv_in", "cv_out"):
        response = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition", json={"status": target}
        )
        assert response.status_code == 200, response.text
    return submission


def _open_tasks_for_submission(client: TestClient, submission_id: str) -> list[dict]:
    tasks = client.get(f"/api/v1/tasks?submission_id={submission_id}").json()
    items = tasks["items"] if isinstance(tasks, dict) else tasks
    return [task for task in items if task["status"] in ("open", "in_progress")]


def test_previous_auto_follow_up_is_closed_on_next_status_change(client: TestClient) -> None:
    submission = _create_submission_at_cv_out(client)
    open_tasks = _open_tasks_for_submission(client, submission["id"])
    assert any(task["title"] == "CV-Out nachfassen" for task in open_tasks)

    response = client.patch(
        f"/api/v1/submissions/{submission['id']}/transition", json={"status": "interview"}
    )
    assert response.status_code == 200, response.text

    open_tasks_after = _open_tasks_for_submission(client, submission["id"])
    assert not any(task["title"] == "CV-Out nachfassen" for task in open_tasks_after)
    assert any(task["title"] == "Interviewfeedback nachfassen" for task in open_tasks_after)


def test_manually_created_task_with_same_title_is_not_closed(client: TestClient) -> None:
    submission = _create_submission_at_cv_out(client)

    manual_task = client.post(
        "/api/v1/tasks",
        json={
            "candidate_submission_id": submission["id"],
            "title": "CV-Out nachfassen",
            "description": "Manuell von Hand angelegt - kein automatisches Follow-up",
        },
    ).json()

    client.patch(f"/api/v1/submissions/{submission['id']}/transition", json={"status": "interview"})

    manual_task_after = client.get(f"/api/v1/tasks/{manual_task['id']}").json()
    assert manual_task_after["status"] == "open"


def test_cancelling_a_process_also_closes_its_stale_auto_follow_up(client: TestClient) -> None:
    submission = _create_submission_at_cv_out(client)
    open_tasks = _open_tasks_for_submission(client, submission["id"])
    assert any(task["title"] == "CV-Out nachfassen" for task in open_tasks)

    response = client.patch(
        f"/api/v1/submissions/{submission['id']}/transition",
        json={"status": "cancelled", "cancellation_reason": "candidate_rejected"},
    )
    assert response.status_code == 200, response.text

    open_tasks_after = _open_tasks_for_submission(client, submission["id"])
    assert not any(task["title"] == "CV-Out nachfassen" for task in open_tasks_after)
