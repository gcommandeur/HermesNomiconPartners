from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient


def test_cockpit_and_email_templates(client: TestClient) -> None:
    cockpit_response = client.get("/api/v1/cockpit?period=week")
    assert cockpit_response.status_code == 200
    cockpit = cockpit_response.json()
    assert cockpit["period"] == "week"
    assert cockpit["kpis"]["submissions"] == 0
    assert "submission_to_interview" in cockpit["rates"]

    templates_response = client.get("/api/v1/email-templates")
    assert templates_response.status_code == 200
    templates = templates_response.json()
    assert len(templates) >= 10
    assert any(item["key"] == "candidate_submission" for item in templates)


def test_cockpit_hot_processes_and_important_include_candidate_and_client_names(
    client: TestClient,
) -> None:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Max", "last_name": "Mustermann"}
    ).json()
    company = client.post("/api/v1/clients", json={"name": "ACME GmbH"}).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    for target in ["cv_in", "cv_out", "interview"]:
        response = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition", json={"status": target}
        )
        assert response.status_code == 200, response.text

    cockpit = client.get("/api/v1/cockpit?period=week").json()
    hot_titles = [item["title"] for item in cockpit["hot_processes"]]
    assert any("Max Mustermann" in title and "ACME GmbH" in title for title in hot_titles)

    important_details = [item["detail"] for item in cockpit["important"]]
    assert any("Max Mustermann" in detail for detail in important_details)


def test_cockpit_sourcing_funnel_has_no_data_until_a_metric_is_recorded(
    client: TestClient,
) -> None:
    empty = client.get("/api/v1/cockpit?period=week").json()
    assert empty["sourcing"]["has_data"] is False
    assert empty["sourcing"]["pitches"] == 0
    assert empty["sourcing"]["pitch_to_response_rate"] is None

    today = datetime.now(UTC).date()
    metric = client.post(
        "/api/v1/sourcing-metrics",
        json={
            "period_start": str(today - timedelta(days=1)),
            "period_end": str(today),
            "source": "LinkedIn",
            "pitches": 40,
            "responses": 10,
            "positive_responses": 4,
            "qualification_calls": 3,
        },
    )
    assert metric.status_code == 201

    filled = client.get("/api/v1/cockpit?period=week").json()
    assert filled["sourcing"]["has_data"] is True
    assert filled["sourcing"]["pitches"] == 40
    assert filled["sourcing"]["responses"] == 10
    assert filled["sourcing"]["pitch_to_response_rate"] == 25.0
    assert filled["sourcing"]["response_to_qualification_call_rate"] == 30.0


def test_profile_suggestion_is_an_editable_draft(client: TestClient) -> None:
    candidate_response = client.post(
        "/api/v1/candidates",
        json={
            "candidate_number": "1001",
            "first_name": "Erika",
            "last_name": "Muster",
            "job_title": "Steuerberaterin",
            "qualification": "Steuerberaterexamen",
            "city": "Stuttgart",
            "cv_available": True,
        },
    )
    candidate_id = candidate_response.json()["id"]

    response = client.post(f"/api/v1/candidates/{candidate_id}/profile-suggestion")
    assert response.status_code == 200
    suggestion = response.json()
    assert suggestion["is_draft"] is True
    assert "Steuerberaterin" in suggestion["text"]


def test_activities_and_tasks_filter_by_candidate_id(client: TestClient) -> None:
    candidate_a = client.post(
        "/api/v1/candidates", json={"first_name": "Anna", "last_name": "A"}
    ).json()
    candidate_b = client.post(
        "/api/v1/candidates", json={"first_name": "Bea", "last_name": "B"}
    ).json()
    client.post(
        "/api/v1/activities",
        json={
            "candidate_id": candidate_a["id"],
            "activity_type": "note",
            "subject": "Anruf mit Anna",
            "occurred_at": "2026-06-01T10:00:00Z",
        },
    )
    client.post(
        "/api/v1/activities",
        json={
            "candidate_id": candidate_b["id"],
            "activity_type": "note",
            "subject": "Anruf mit Bea",
            "occurred_at": "2026-06-01T10:00:00Z",
        },
    )
    client.post(
        "/api/v1/tasks",
        json={"candidate_id": candidate_a["id"], "title": "Follow-up Anna"},
    )
    client.post(
        "/api/v1/tasks",
        json={"candidate_id": candidate_b["id"], "title": "Follow-up Bea"},
    )

    activities = client.get(f"/api/v1/activities?candidate_id={candidate_a['id']}").json()
    assert len(activities) == 1
    assert activities[0]["subject"] == "Anruf mit Anna"

    tasks = client.get(f"/api/v1/tasks?candidate_id={candidate_a['id']}").json()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Follow-up Anna"


def test_document_generic_filename_flag_is_computed_on_create(client: TestClient) -> None:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Generic", "last_name": "Filename"}
    ).json()
    generic = client.post(
        "/api/v1/documents",
        json={
            "owner_type": "candidate",
            "owner_id": candidate["id"],
            "document_type": "cv",
            "filename": "Lebenslauf (2).pdf",
            "storage_key": "candidates/generic.pdf",
        },
    )
    assert generic.status_code == 201, generic.text
    assert generic.json()["has_generic_filename"] is True

    specific = client.post(
        "/api/v1/documents",
        json={
            "owner_type": "candidate",
            "owner_id": candidate["id"],
            "document_type": "cv",
            "filename": "lebenslauf-hans-mueller.pdf",
            "storage_key": "candidates/specific.pdf",
        },
    )
    assert specific.status_code == 201, specific.text
    assert specific.json()["has_generic_filename"] is False


def test_documents_filter_by_owner(client: TestClient) -> None:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Doc", "last_name": "Owner"}
    ).json()
    client.post(
        "/api/v1/documents",
        json={
            "owner_type": "candidate",
            "owner_id": candidate["id"],
            "document_type": "cv",
            "filename": "cv.pdf",
            "storage_key": "candidates/cv.pdf",
        },
    )
    client.post(
        "/api/v1/documents",
        json={
            "owner_type": "client",
            "owner_id": candidate["id"],
            "document_type": "terms",
            "filename": "agb.pdf",
            "storage_key": "clients/agb.pdf",
        },
    )

    documents = client.get(
        f"/api/v1/documents?owner_type=candidate&owner_id={candidate['id']}"
    ).json()
    assert len(documents) == 1
    assert documents[0]["filename"] == "cv.pdf"
