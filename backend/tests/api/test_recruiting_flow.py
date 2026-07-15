from fastapi.testclient import TestClient


def _create_submission(client: TestClient, company_name: str = "Kanzlei Alpha") -> dict:
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Test", "last_name": "Candidate"},
    ).json()
    company = client.post(
        "/api/v1/clients",
        json={"name": company_name, "status": "active"},
    ).json()
    response = client.post(
        "/api/v1/submissions",
        json={
            "candidate_id": candidate["id"],
            "client_company_id": company["id"],
        },
    )
    assert response.status_code == 201
    return response.json()


def _transition(client: TestClient, submission_id: str, status: str, **extra: object) -> dict:
    response = client.patch(
        f"/api/v1/submissions/{submission_id}/transition",
        json={"status": status, **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_invalid_submission_transition_is_rejected(client: TestClient) -> None:
    submission = _create_submission(client)

    response = client.patch(
        f"/api/v1/submissions/{submission['id']}/transition",
        json={"status": "placement"},
    )

    assert response.status_code == 422
    assert "not allowed" in response.json()["detail"]


def test_cancellation_requires_reason(client: TestClient) -> None:
    submission = _create_submission(client)

    response = client.patch(
        f"/api/v1/submissions/{submission['id']}/transition",
        json={"status": "cancelled"},
    )
    assert response.status_code == 422
    assert "cancellation_reason" in response.json()["detail"]

    cancelled = _transition(
        client, submission["id"], "cancelled", cancellation_reason="candidate_ghosting"
    )
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancellation_reason"] == "candidate_ghosting"


def test_client_not_required_before_interview_but_required_from_interview_on(
    client: TestClient,
) -> None:
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Kein", "last_name": "Kanzlei"},
    ).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"]},
    )
    assert submission.status_code == 201
    submission_id = submission.json()["id"]
    assert submission.json()["client_company_id"] is None

    _transition(client, submission_id, "cv_in")
    without_client = client.patch(
        f"/api/v1/submissions/{submission_id}/transition",
        json={"status": "cv_out"},
    )
    assert without_client.status_code == 200
    assert without_client.json()["client_company_id"] is None

    blocked = client.patch(
        f"/api/v1/submissions/{submission_id}/transition",
        json={"status": "interview"},
    )
    assert blocked.status_code == 422
    assert "Kanzlei" in blocked.json()["detail"]

    company = client.post("/api/v1/clients", json={"name": "Nachtraeglich AG"}).json()
    with_client = client.patch(
        f"/api/v1/submissions/{submission_id}/transition",
        json={"status": "interview", "client_company_id": company["id"]},
    )
    assert with_client.status_code == 200
    assert with_client.json()["client_company_id"] == company["id"]


def test_complete_recruiting_flow_with_fee_activity_and_audit(
    client: TestClient,
) -> None:
    submission = _create_submission(client)
    submission_id = submission["id"]

    _transition(client, submission_id, "cv_in")
    _transition(client, submission_id, "cv_out")

    feedback = client.post(
        f"/api/v1/submissions/{submission_id}/feedback",
        json={
            "feedback_type": "client",
            "feedback_text": "Please arrange an interview.",
            "received_at": "2026-06-28T10:00:00Z",
            "next_step": "Interview",
        },
    )
    assert feedback.status_code == 201

    _transition(client, submission_id, "interview")
    interview = client.post(
        f"/api/v1/submissions/{submission_id}/interviews",
        json={
            "scheduled_at": "2026-07-01T09:00:00Z",
            "interview_type": "video",
            "location_or_link": "https://example.com/meeting",
            "participants": ["Candidate", "Client"],
        },
    )
    assert interview.status_code == 201
    assert client.get(f"/api/v1/submissions/{submission_id}").json()["status"] == "interview"

    _transition(client, submission_id, "offer")
    offer = client.post(
        f"/api/v1/submissions/{submission_id}/offers",
        json={
            "offered_salary": "70000.00",
            "start_date": "2026-09-01",
            "offer_status": "received",
        },
    )
    assert offer.status_code == 201
    assert client.get(f"/api/v1/submissions/{submission_id}").json()["status"] == "offer"

    _transition(client, submission_id, "placement")
    placement = client.post(
        f"/api/v1/submissions/{submission_id}/placement",
        json={
            "start_date": "2026-09-01",
            "final_salary": "70000.00",
            "fee_percentage": "27.00",
            "guarantee_period_months": 6,
        },
    )
    assert placement.status_code == 201
    placement_data = placement.json()
    assert placement_data["calculated_fee"] == "18900.00"
    assert client.get(f"/api/v1/submissions/{submission_id}").json()["status"] == "placement"

    fee = client.post(
        f"/api/v1/placements/{placement_data['id']}/fees",
        json={"amount_net": "18900.00"},
    )
    assert fee.status_code == 201
    assert fee.json()["vat_rate"] == "19.00"
    assert fee.json()["amount_gross"] == "22491.00"

    activity_types = {item["activity_type"] for item in client.get("/api/v1/activities").json()}
    assert {
        "feedback_received",
        "interview_scheduled",
        "offer_received",
        "placement_created",
        "fee_calculated",
        "submission_status_changed",
    }.issubset(activity_types)

    audit_actions = {item["action"] for item in client.get("/api/v1/audit-logs").json()}
    assert "status_changed" in audit_actions
    assert "placement_created" in audit_actions
    assert "fee_calculated" in audit_actions


def test_placement_defaults_to_client_fee_percentage_when_omitted(client: TestClient) -> None:
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Fee", "last_name": "Default"},
    ).json()
    company = client.post(
        "/api/v1/clients",
        json={"name": "Kanzlei Fee Default", "fee_percentage": "30.00"},
    ).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()

    _transition(client, submission["id"], "cv_in")
    _transition(client, submission["id"], "cv_out")
    _transition(client, submission["id"], "interview")
    _transition(client, submission["id"], "offer")
    _transition(client, submission["id"], "placement")

    placement = client.post(
        f"/api/v1/submissions/{submission['id']}/placement",
        json={"start_date": "2026-09-01", "final_salary": "70000.00"},
    )
    assert placement.status_code == 201, placement.text
    data = placement.json()
    assert data["fee_percentage"] == "30.00"
    assert data["calculated_fee"] == "21000.00"


def test_interview_follow_up_aligns_with_scheduled_interview_not_status_change(
    client: TestClient,
) -> None:
    submission = _create_submission(client)
    _transition(client, submission["id"], "cv_in")
    _transition(client, submission["id"], "cv_out")
    _transition(client, submission["id"], "interview")

    provisional_follow_up = client.get(f"/api/v1/submissions/{submission['id']}").json()[
        "follow_up_at"
    ]

    far_future_interview = client.post(
        f"/api/v1/submissions/{submission['id']}/interviews",
        json={
            "scheduled_at": "2026-08-15T09:00:00Z",
            "interview_type": "onsite",
        },
    )
    assert far_future_interview.status_code == 201, far_future_interview.text

    updated = client.get(f"/api/v1/submissions/{submission['id']}").json()
    assert updated["follow_up_at"] != provisional_follow_up
    assert updated["follow_up_at"].startswith("2026-08-16")

    tasks = client.get("/api/v1/tasks").json()
    follow_up_tasks = [
        task
        for task in tasks
        if task["candidate_submission_id"] == submission["id"]
        and task["title"] == "Interviewfeedback nachfassen"
    ]
    assert len(follow_up_tasks) == 1
    assert follow_up_tasks[0]["due_at"].startswith("2026-08-16")


def test_placement_creates_referral_follow_up_task_in_addition_to_generic_one(
    client: TestClient,
) -> None:
    submission = _create_submission(client)
    _transition(client, submission["id"], "cv_in")
    _transition(client, submission["id"], "cv_out")
    _transition(client, submission["id"], "interview")
    _transition(client, submission["id"], "offer")
    _transition(client, submission["id"], "placement")

    tasks = client.get("/api/v1/tasks").json()
    submission_tasks = [
        task for task in tasks if task["candidate_submission_id"] == submission["id"]
    ]
    titles = {task["title"] for task in submission_tasks}
    assert "Placement und Rechnung nachverfolgen" in titles
    assert "Nach Empfehlung fragen" in titles


def test_submission_filters_and_pagination(client: TestClient) -> None:
    first = _create_submission(client, "Kanzlei Filter One")
    second = _create_submission(client, "Kanzlei Filter Two")
    _transition(client, first["id"], "cv_in")

    page = client.get("/api/v1/submissions?status=cv_in&limit=1&offset=0")

    assert page.status_code == 200
    assert page.json()["total_count"] == 1
    assert page.json()["limit"] == 1
    assert page.json()["offset"] == 0
    assert page.json()["items"][0]["id"] == first["id"]
    assert second["id"] != first["id"]
