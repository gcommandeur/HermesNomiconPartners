import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.task import Task


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


def test_email_templates_have_distinct_specific_bodies(client: TestClient) -> None:
    """Regressionsschutz: templates() lieferte frueher fuer JEDEN Key
    denselben generischen body-Text - nur der subject unterschied sich."""
    templates = client.get("/api/v1/email-templates").json()
    by_key = {item["key"]: item for item in templates}

    expected_keys = {
        "post_qualification_call",
        "candidate_submission",
        "interview_confirmation",
        "interview_feedback",
        "interview_feedback_candidate",
    }
    assert expected_keys.issubset(by_key.keys())

    bodies = [item["body"] for item in templates]
    assert len(bodies) == len(set(bodies)), "jede Vorlage muss einen eigenen body-Text haben"

    post_qc = by_key["post_qualification_call"]
    assert post_qc["subject"] == "Vielen Dank für das Gespräch, {candidate}"
    assert "{next_step}" in post_qc["body"]
    assert "{candidate}" in post_qc["body"]

    submission = by_key["candidate_submission"]
    assert submission["subject"] == "Profilvorstellung: {candidate} – {role}"
    assert "{short_profile}" in submission["body"]
    assert "{salary}" in submission["body"]
    assert "{notice_period}" in submission["body"]

    interview_confirmation = by_key["interview_confirmation"]
    assert interview_confirmation["subject"] == "Interviewtermin bei {client}"

    interview_feedback = by_key["interview_feedback"]
    assert interview_feedback["subject"] == "Kurzes Feedback zum Interview mit {candidate}"

    interview_feedback_candidate = by_key["interview_feedback_candidate"]
    assert interview_feedback_candidate["subject"] == "Rückmeldung zu Ihrem Interview bei {client}"
    assert "{next_step}" in interview_feedback_candidate["body"]


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


def test_cockpit_important_task_items_carry_task_id_for_dashboard_actions(
    client: TestClient,
) -> None:
    """Die Dashboard-To-Do-Sektion (snooze/resolve) braucht die Task-ID in
    jedem "important"-Eintrag vom kind="task"."""
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Erika", "last_name": "Musterfrau"}
    ).json()
    task = client.post(
        "/api/v1/tasks",
        json={"candidate_id": candidate["id"], "title": "LinkedIn-Antwort: Erika Musterfrau"},
    ).json()

    cockpit = client.get("/api/v1/cockpit?period=week").json()
    matching = [item for item in cockpit["important"] if item.get("task_id") == task["id"]]
    assert len(matching) == 1
    assert matching[0]["kind"] == "task"
    assert matching[0]["candidate_id"] == candidate["id"]


def test_cockpit_important_excludes_snoozed_tasks(client: TestClient) -> None:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Zurueck", "last_name": "Gestellt"}
    ).json()
    task = client.post(
        "/api/v1/tasks",
        json={"candidate_id": candidate["id"], "title": "LinkedIn-Antwort: Zurueck Gestellt"},
    ).json()

    before = client.get("/api/v1/cockpit?period=week").json()
    assert any(item.get("task_id") == task["id"] for item in before["important"])

    client.post(f"/api/v1/tasks/{task['id']}/snooze", json={"days": 3})

    after = client.get("/api/v1/cockpit?period=week").json()
    assert not any(item.get("task_id") == task["id"] for item in after["important"])


def test_cockpit_important_resolves_names_via_submission_when_task_fields_are_null(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Aeltere Task-Zeilen (vor Einfuehrung von candidate_id/client_company_id
    auf automatischen Follow-ups) haben diese Spalten leer, obwohl die
    verknuepfte Submission Kandidat/Kanzlei kennt - die Uebersicht muss den
    Namen trotzdem ueber candidate_submission_id auflösen, statt einen
    namenlosen Eintrag zu zeigen (siehe services/operational.py::build)."""
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Erika", "last_name": "Beispiel"}
    ).json()
    company = client.post("/api/v1/clients", json={"name": "Beispiel Steuerberatung"}).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()

    with session_factory() as session:
        session.add(
            Task(
                candidate_id=None,
                client_company_id=None,
                candidate_submission_id=uuid.UUID(submission["id"]),
                title="Interviewfeedback nachfassen",
                description="Automatisch aus dem Prozessstatus erzeugtes Follow-up",
                due_at=datetime.now(UTC),
            )
        )
        session.commit()

    cockpit = client.get("/api/v1/cockpit?period=week").json()
    important_details = [item["detail"] for item in cockpit["important"]]
    assert any(
        "Erika Beispiel" in detail and "Beispiel Steuerberatung" in detail
        for detail in important_details
    )


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


def test_recruiting_kpis_are_null_until_data_exists(client: TestClient) -> None:
    cockpit = client.get("/api/v1/cockpit?period=month").json()
    kpis = cockpit["recruiting_kpis"]
    assert kpis["time_to_fill_days"] is None
    assert kpis["time_to_interview_days"] is None
    assert kpis["average_fee_per_placement"] is None


def test_recruiting_kpis_time_to_fill_time_to_interview_and_average_fee(
    client: TestClient, session_factory
) -> None:
    """time_to_fill_days/time_to_interview_days/average_fee_per_placement
    laufen ueber den GESAMTEN historischen Bestand (nicht period-begrenzt) -
    siehe CockpitService._recruiting_kpis. Backdatiert submission.created_at
    direkt in der DB, um einen deterministischen Tage-Delta zu erzwingen
    (created_at ist server-seitig gesetzt, ueber die API nicht steuerbar)."""
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "KPI", "last_name": "Test"}
    ).json()
    company = client.post("/api/v1/clients", json={"name": "Kanzlei KPI"}).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    for status in ("cv_in", "cv_out", "interview", "offer", "placement"):
        response = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition", json={"status": status}
        )
        assert response.status_code == 200, response.text

    placement = client.post(
        f"/api/v1/submissions/{submission['id']}/placement",
        json={"start_date": "2026-09-01", "final_salary": "60000.00", "fee_percentage": "25.00"},
    ).json()

    with session_factory() as session:
        db_submission = session.get(CandidateSubmission, uuid.UUID(submission["id"]))
        assert db_submission is not None
        db_submission.created_at = datetime.now(UTC) - timedelta(days=12)
        session.commit()

    cockpit = client.get("/api/v1/cockpit?period=month").json()
    kpis = cockpit["recruiting_kpis"]
    assert kpis["time_to_fill_days"] is not None
    assert 11 <= kpis["time_to_fill_days"] <= 13
    assert kpis["time_to_interview_days"] is not None
    assert 11 <= kpis["time_to_interview_days"] <= 13
    assert kpis["average_fee_per_placement"] == float(placement["calculated_fee"])
