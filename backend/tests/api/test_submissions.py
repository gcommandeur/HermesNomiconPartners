from fastapi.testclient import TestClient


def test_candidate_can_be_submitted_to_multiple_clients(client: TestClient) -> None:
    candidate = client.post(
        "/api/v1/candidates",
        json={
            "first_name": "Erika",
            "last_name": "Muster",
            "job_title": "Steuerberaterin",
        },
    ).json()
    client_one = client.post(
        "/api/v1/clients",
        json={"name": "Kanzlei Nord", "status": "active"},
    ).json()
    client_two = client.post(
        "/api/v1/clients",
        json={"name": "Kanzlei Süd", "status": "active"},
    ).json()

    first_submission = client.post(
        "/api/v1/submissions",
        json={
            "candidate_id": candidate["id"],
            "client_company_id": client_one["id"],
        },
    )
    second_submission = client.post(
        "/api/v1/submissions",
        json={
            "candidate_id": candidate["id"],
            "client_company_id": client_two["id"],
        },
    )

    assert first_submission.status_code == 201
    assert second_submission.status_code == 201
    assert first_submission.json()["id"] != second_submission.json()["id"]

    submissions = client.get(f"/api/v1/candidates/{candidate['id']}/submissions")
    assert submissions.status_code == 200
    assert len(submissions.json()) == 2


def test_duplicate_active_submission_is_rejected_and_status_is_audited(
    client: TestClient,
) -> None:
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Max", "last_name": "Beispiel"},
    ).json()
    company = client.post(
        "/api/v1/clients",
        json={"name": "Kanzlei West"},
    ).json()
    payload = {
        "candidate_id": candidate["id"],
        "client_company_id": company["id"],
    }

    submission = client.post("/api/v1/submissions", json=payload)
    duplicate = client.post("/api/v1/submissions", json=payload)

    assert submission.status_code == 201
    assert duplicate.status_code == 409

    client.patch(
        f"/api/v1/submissions/{submission.json()['id']}/transition",
        json={"status": "qualification_call"},
    )
    update = client.patch(
        f"/api/v1/submissions/{submission.json()['id']}/transition",
        json={"status": "cv_in"},
    )
    assert update.status_code == 200
    assert update.json()["status"] == "cv_in"

    activities = client.get("/api/v1/activities")
    assert activities.status_code == 200
    activity_types = {item["activity_type"] for item in activities.json()}
    assert activity_types == {
        "submission_created",
        "submission_status_changed",
    }
