from datetime import date, timedelta

from fastapi.testclient import TestClient


def _create_placed_submission(client: TestClient, name_suffix: str) -> dict:
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Warranty", "last_name": name_suffix},
    ).json()
    company = client.post(
        "/api/v1/clients", json={"name": f"Kanzlei Warranty {name_suffix}"}
    ).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    for target in ["cv_in", "cv_out", "interview", "offer", "placement"]:
        response = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition", json={"status": target}
        )
        assert response.status_code == 200, response.text
    return submission


def test_placement_warranty_end_date_and_status_are_computed(client: TestClient) -> None:
    submission = _create_placed_submission(client, "Laufend")
    start = date.today() - timedelta(days=30)
    placement = client.post(
        f"/api/v1/submissions/{submission['id']}/placement",
        json={
            "start_date": start.isoformat(),
            "final_salary": "70000.00",
            "fee_percentage": "27.00",
            "guarantee_period_months": 6,
        },
    )
    assert placement.status_code == 201, placement.text
    data = placement.json()
    assert data["warranty_status"] == "laufend"
    assert date.fromisoformat(data["warranty_end_date"]) > date.today()

    # Follow-up task was scheduled automatically.
    tasks = client.get("/api/v1/tasks").json()
    warranty_tasks = [
        task
        for task in tasks
        if task["candidate_submission_id"] == submission["id"]
        and task["title"] == "Gewährleistung läuft bald ab"
    ]
    assert len(warranty_tasks) == 1


def test_placement_warranty_bald_ablaufend_and_abgelaufen(client: TestClient) -> None:
    soon_submission = _create_placed_submission(client, "BaldAblaufend")
    soon_start = date.today() - timedelta(days=5 * 30 - 10)
    soon = client.post(
        f"/api/v1/submissions/{soon_submission['id']}/placement",
        json={
            "start_date": soon_start.isoformat(),
            "final_salary": "70000.00",
            "fee_percentage": "27.00",
            "guarantee_period_months": 5,
        },
    )
    assert soon.status_code == 201, soon.text
    assert soon.json()["warranty_status"] == "bald_ablaufend"

    expired_submission = _create_placed_submission(client, "Abgelaufen")
    expired = client.post(
        f"/api/v1/submissions/{expired_submission['id']}/placement",
        json={
            "start_date": "2020-01-01",
            "final_salary": "70000.00",
            "fee_percentage": "27.00",
            "guarantee_period_months": 6,
        },
    )
    assert expired.status_code == 201, expired.text
    assert expired.json()["warranty_status"] == "abgelaufen"


def test_active_warranties_overview_excludes_expired_and_sorts_by_expiry(
    client: TestClient,
) -> None:
    expired_submission = _create_placed_submission(client, "OverviewExpired")
    client.post(
        f"/api/v1/submissions/{expired_submission['id']}/placement",
        json={
            "start_date": "2020-01-01",
            "final_salary": "60000.00",
            "fee_percentage": "27.00",
            "guarantee_period_months": 6,
        },
    )

    soon_submission = _create_placed_submission(client, "OverviewSoon")
    soon_start = date.today() - timedelta(days=5 * 30)
    client.post(
        f"/api/v1/submissions/{soon_submission['id']}/placement",
        json={
            "start_date": soon_start.isoformat(),
            "final_salary": "60000.00",
            "fee_percentage": "27.00",
            "guarantee_period_months": 6,
        },
    )

    later_submission = _create_placed_submission(client, "OverviewLater")
    later_start = date.today()
    client.post(
        f"/api/v1/submissions/{later_submission['id']}/placement",
        json={
            "start_date": later_start.isoformat(),
            "final_salary": "60000.00",
            "fee_percentage": "27.00",
            "guarantee_period_months": 6,
        },
    )

    response = client.get("/api/v1/placements/active-warranties")
    assert response.status_code == 200
    submission_ids = [item["submission_id"] for item in response.json()]
    assert expired_submission["id"] not in submission_ids
    assert submission_ids.index(soon_submission["id"]) < submission_ids.index(
        later_submission["id"]
    )
