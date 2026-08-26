"""Tests fuer den Quick-Log-Endpoint und die Stage-Summary (siehe
services/recruiting.py::quick_log/stage_summary und
services/submissions.py::ALLOWED_TRANSITIONS).

Die Pipeline beginnt seit Phase 5a direkt bei "qualification_call" - die
zuvor vorgeschaltete "pitch"-Stufe (Task #136) wurde bewusst wieder entfernt
(siehe models/enums.py::SubmissionStatus)."""

from fastapi.testclient import TestClient


def _create_candidate(client: TestClient, last_name: str = "Test") -> dict:
    response = client.post(
        "/api/v1/candidates",
        json={"first_name": "Test", "last_name": last_name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_new_submission_starts_at_qualification_call(client: TestClient) -> None:
    candidate = _create_candidate(client, "StartsAtQualiCall")
    response = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"]},
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "qualification_call"


def test_qualification_call_can_only_transition_to_cv_in_or_cancelled(
    client: TestClient,
) -> None:
    candidate = _create_candidate(client, "QualiCallTransition")
    submission = client.post(
        "/api/v1/submissions", json={"candidate_id": candidate["id"]}
    ).json()

    blocked = client.patch(
        f"/api/v1/submissions/{submission['id']}/transition",
        json={"status": "cv_out"},
    )
    assert blocked.status_code == 422
    assert "not allowed" in blocked.json()["detail"]

    allowed = client.patch(
        f"/api/v1/submissions/{submission['id']}/transition",
        json={"status": "cv_in"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "cv_in"


def test_quick_log_qualification_call_without_existing_submission_creates_and_advances(
    client: TestClient,
) -> None:
    candidate = _create_candidate(client, "QuickLogQualiCall")
    response = client.post(
        f"/api/v1/candidates/{candidate['id']}/quick-log",
        json={
            "stage": "qualification_call",
            "feedback_type": "internal",
            "feedback_text": "Quali-Call durchgefuehrt.",
            "received_at": "2026-07-02T09:00:00",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["submission"]["status"] == "qualification_call"
    assert body["submission"]["candidate_id"] == candidate["id"]
    assert body["submission"]["client_company_id"] is None
    assert body["feedback"]["stage"] == "qualification_call"
    assert body["feedback"]["feedback_text"] == "Quali-Call durchgefuehrt."

    submissions = client.get(f"/api/v1/candidates/{candidate['id']}/submissions").json()
    assert len(submissions) == 1


def test_quick_log_reuses_open_submission_instead_of_creating_a_second_one(
    client: TestClient,
) -> None:
    candidate = _create_candidate(client, "QuickLogReuse")

    first = client.post(
        f"/api/v1/candidates/{candidate['id']}/quick-log",
        json={
            "stage": "qualification_call",
            "feedback_type": "internal",
            "feedback_text": "Quali-Call-Notiz eins.",
            "received_at": "2026-07-01T09:00:00",
        },
    ).json()

    second = client.post(
        f"/api/v1/candidates/{candidate['id']}/quick-log",
        json={
            "stage": "cv_in",
            "feedback_type": "internal",
            "feedback_text": "Shortlist-Notiz.",
            "received_at": "2026-07-05T09:00:00",
        },
    ).json()

    # Dieselbe Submission wurde weitergefuehrt statt eine zweite anzulegen.
    assert first["submission"]["id"] == second["submission"]["id"]
    assert second["submission"]["status"] == "cv_in"

    submissions = client.get(f"/api/v1/candidates/{candidate['id']}/submissions").json()
    assert len(submissions) == 1

    feedback_entries = client.get(
        f"/api/v1/submissions/{first['submission']['id']}/feedback"
    ).json()
    assert len(feedback_entries) == 2
    stages = {entry["stage"] for entry in feedback_entries}
    assert stages == {"qualification_call", "cv_in"}


def test_quick_log_qualification_call_again_does_not_error_when_already_there(
    client: TestClient,
) -> None:
    candidate = _create_candidate(client, "QuickLogIdempotent")
    client.post(
        f"/api/v1/candidates/{candidate['id']}/quick-log",
        json={
            "stage": "qualification_call",
            "feedback_type": "internal",
            "feedback_text": "Erster Call.",
            "received_at": "2026-07-01T09:00:00",
        },
    )
    second = client.post(
        f"/api/v1/candidates/{candidate['id']}/quick-log",
        json={
            "stage": "qualification_call",
            "feedback_type": "internal",
            "feedback_text": "Zweiter Call, gleiche Stufe.",
            "received_at": "2026-07-08T09:00:00",
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["submission"]["status"] == "qualification_call"

    submissions = client.get(f"/api/v1/candidates/{candidate['id']}/submissions").json()
    assert len(submissions) == 1


def test_quick_log_ignores_submissions_already_linked_to_a_client(
    client: TestClient,
) -> None:
    candidate = _create_candidate(client, "QuickLogIgnoresClient")
    company = client.post("/api/v1/clients", json={"name": "Kanzlei QuickLog"}).json()
    client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    )

    response = client.post(
        f"/api/v1/candidates/{candidate['id']}/quick-log",
        json={
            "stage": "qualification_call",
            "feedback_type": "internal",
            "feedback_text": "Neuer, separater Quali-Call.",
            "received_at": "2026-07-01T09:00:00",
        },
    )
    assert response.status_code == 200, response.text

    submissions = client.get(f"/api/v1/candidates/{candidate['id']}/submissions").json()
    assert len(submissions) == 2


def test_quick_log_rejects_stage_outside_allowed_set(
    client: TestClient,
) -> None:
    candidate = _create_candidate(client, "QuickLogInvalidStage")
    response = client.post(
        f"/api/v1/candidates/{candidate['id']}/quick-log",
        json={
            "stage": "interview",
            "feedback_type": "internal",
            "feedback_text": "Sollte fehlschlagen.",
            "received_at": "2026-07-01T09:00:00",
        },
    )
    assert response.status_code == 422
    assert "quick-log" in response.json()["detail"]


def test_quick_log_can_advance_directly_to_cv_out_without_existing_submission(
    client: TestClient,
) -> None:
    candidate = _create_candidate(client, "QuickLogToCvOut")
    response = client.post(
        f"/api/v1/candidates/{candidate['id']}/quick-log",
        json={
            "stage": "cv_out",
            "feedback_type": "internal",
            "feedback_text": "Direkt bis CV-Sent vorgezogen.",
            "received_at": "2026-07-01T09:00:00",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["submission"]["status"] == "cv_out"
    assert body["feedback"]["stage"] == "cv_out"

    submissions = client.get(f"/api/v1/candidates/{candidate['id']}/submissions").json()
    assert len(submissions) == 1


def test_quick_log_advances_existing_qualification_call_submission_to_cv_in(
    client: TestClient,
) -> None:
    candidate = _create_candidate(client, "QuickLogToCvIn")
    client.post(
        f"/api/v1/candidates/{candidate['id']}/quick-log",
        json={
            "stage": "qualification_call",
            "feedback_type": "internal",
            "feedback_text": "Quali-Call-Notiz.",
            "received_at": "2026-07-01T09:00:00",
        },
    )
    response = client.post(
        f"/api/v1/candidates/{candidate['id']}/quick-log",
        json={
            "stage": "cv_in",
            "feedback_type": "internal",
            "feedback_text": "Shortlist erreicht.",
            "received_at": "2026-07-03T09:00:00",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["submission"]["status"] == "cv_in"
    assert body["feedback"]["stage"] == "cv_in"

    submissions = client.get(f"/api/v1/candidates/{candidate['id']}/submissions").json()
    assert len(submissions) == 1


def test_feedback_with_target_status_transitions_submission_and_sets_stage(
    client: TestClient,
) -> None:
    candidate = _create_candidate(client, "TargetStatusTransition")
    submission = client.post(
        "/api/v1/submissions", json={"candidate_id": candidate["id"]}
    ).json()
    assert submission["status"] == "qualification_call"

    response = client.post(
        f"/api/v1/submissions/{submission['id']}/feedback",
        json={
            "feedback_type": "internal",
            "feedback_text": "Shortlist erreicht.",
            "received_at": "2026-07-02T09:00:00",
            "target_status": "cv_in",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["feedback"]["stage"] == "cv_in"
    assert body["submission"]["status"] == "cv_in"


def test_feedback_with_target_status_equal_to_current_status_does_not_transition(
    client: TestClient,
) -> None:
    candidate = _create_candidate(client, "TargetStatusNoop")
    submission = client.post(
        "/api/v1/submissions", json={"candidate_id": candidate["id"]}
    ).json()

    response = client.post(
        f"/api/v1/submissions/{submission['id']}/feedback",
        json={
            "feedback_type": "internal",
            "feedback_text": "Weitere Quali-Call-Notiz, kein Statuswechsel.",
            "received_at": "2026-07-02T09:00:00",
            "target_status": "qualification_call",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["feedback"]["stage"] == "qualification_call"
    assert body["submission"]["status"] == "qualification_call"


def test_feedback_with_invalid_target_status_transition_is_rejected(
    client: TestClient,
) -> None:
    candidate = _create_candidate(client, "TargetStatusInvalid")
    submission = client.post(
        "/api/v1/submissions", json={"candidate_id": candidate["id"]}
    ).json()

    response = client.post(
        f"/api/v1/submissions/{submission['id']}/feedback",
        json={
            "feedback_type": "internal",
            "feedback_text": "Sollte fehlschlagen - kein Ein-Schritt-Uebergang.",
            "received_at": "2026-07-02T09:00:00",
            "target_status": "cv_out",
        },
    )
    assert response.status_code == 422
    assert "not allowed" in response.json()["detail"]

    # Kein Statuswechsel und keine Notiz wurden angelegt (Transaktion rolled back).
    updated_submission = client.get(f"/api/v1/submissions/{submission['id']}").json()
    assert updated_submission["status"] == "qualification_call"
    feedback_entries = client.get(f"/api/v1/submissions/{submission['id']}/feedback").json()
    assert feedback_entries == []


def test_feedback_with_target_status_outside_allowed_set_is_rejected(
    client: TestClient,
) -> None:
    candidate = _create_candidate(client, "TargetStatusOutsideSet")
    company = client.post("/api/v1/clients", json={"name": "Kanzlei TargetStatus"}).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    for target in ("cv_in", "cv_out", "interview"):
        transitioned = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition", json={"status": target}
        )
        assert transitioned.status_code == 200, transitioned.text

    response = client.post(
        f"/api/v1/submissions/{submission['id']}/feedback",
        json={
            "feedback_type": "internal",
            "feedback_text": "Sollte fehlschlagen - Offer ist kein erlaubtes Feedback-Ziel.",
            "received_at": "2026-07-10T09:00:00",
            "target_status": "offer",
        },
    )
    assert response.status_code == 422
    assert "target_status" in response.json()["detail"]


def test_quick_log_returns_404_for_unknown_candidate(client: TestClient) -> None:
    response = client.post(
        "/api/v1/candidates/00000000-0000-0000-0000-000000000000/quick-log",
        json={
            "stage": "qualification_call",
            "feedback_type": "internal",
            "feedback_text": "Sollte fehlschlagen.",
            "received_at": "2026-07-01T09:00:00",
        },
    )
    assert response.status_code == 404


def test_stage_summary_counts_across_multiple_submissions(client: TestClient) -> None:
    candidate = _create_candidate(client, "StageSummary")

    # Submission A: Quali-Call-Notiz, dann bis Interview weitergefuehrt.
    company_a = client.post("/api/v1/clients", json={"name": "Kanzlei Summary A"}).json()
    submission_a = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company_a["id"]},
    ).json()
    client.post(
        f"/api/v1/submissions/{submission_a['id']}/feedback",
        json={
            "feedback_type": "internal",
            "feedback_text": "Quali-Call A",
            "received_at": "2026-07-01T09:00:00",
            "stage": "qualification_call",
        },
    )
    for target in ("cv_in", "cv_out", "interview"):
        response = client.patch(
            f"/api/v1/submissions/{submission_a['id']}/transition", json={"status": target}
        )
        assert response.status_code == 200, response.text
    client.post(
        f"/api/v1/submissions/{submission_a['id']}/feedback",
        json={
            "feedback_type": "internal",
            "feedback_text": "Shortlist A",
            "received_at": "2026-07-02T09:00:00",
            "stage": "cv_in",
        },
    )
    client.post(
        f"/api/v1/submissions/{submission_a['id']}/interviews",
        json={"scheduled_at": "2026-07-10T10:00:00", "interview_type": "Erstgespraech"},
    )

    # Submission B: zweiter, unabhaengiger Prozess bei einer anderen Kanzlei -
    # nur eine weitere Quali-Call-Notiz.
    company_b = client.post("/api/v1/clients", json={"name": "Kanzlei Summary B"}).json()
    submission_b = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company_b["id"]},
    ).json()
    client.post(
        f"/api/v1/submissions/{submission_b['id']}/feedback",
        json={
            "feedback_type": "internal",
            "feedback_text": "Quali-Call B",
            "received_at": "2026-07-03T09:00:00",
            "stage": "qualification_call",
        },
    )

    summary = client.get(f"/api/v1/candidates/{candidate['id']}/stage-summary")
    assert summary.status_code == 200, summary.text
    data = summary.json()
    assert data["qualification_call"] == 2
    assert data["cv_in"] == 1
    # Submission A wurde per PATCH .../transition (Kanban-Drag) nach cv_out
    # bewegt, OHNE dass dafuer ein SubmissionFeedback-Eintrag mit stage=
    # "cv_out" existiert - stage_summary() zaehlt seit der Umstellung auf
    # die echte Statuswechsel-Historie (AuditLog) trotzdem korrekt 1 statt
    # faelschlich 0 (Nutzer-Feedback "KPIs stimmen nicht", Punkt 3a - genau
    # dieser Fall war der gemeldete Zaehlfehler).
    assert data["cv_out"] == 1
    assert data["interview"] == 1
    assert data["offer"] == 0
    assert data["placement"] == 0


def test_stage_summary_counts_pure_kanban_drag_without_any_feedback(
    client: TestClient,
) -> None:
    """Kernfall des gemeldeten Bugs: ein Prozess wird NUR per Kanban-Drag
    (PATCH .../transition) bewegt, es wird nie irgendein Feedback-Eintrag
    angelegt - jede erreichte Stufe muss trotzdem korrekt gezaehlt werden."""
    candidate = _create_candidate(client, "PureDrag")
    company = client.post("/api/v1/clients", json={"name": "Kanzlei PureDrag"}).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    for target in ("cv_in", "cv_out"):
        response = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition", json={"status": target}
        )
        assert response.status_code == 200, response.text

    summary = client.get(f"/api/v1/candidates/{candidate['id']}/stage-summary").json()

    assert summary["qualification_call"] == 1
    assert summary["cv_in"] == 1
    assert summary["cv_out"] == 1
    assert summary["interview"] == 0


def test_stage_summary_counts_offer_reached_via_transition_alone(
    client: TestClient,
) -> None:
    """Ein Prozess kann per Drag auf 'offer' stehen, OHNE dass je das
    Offer-Formular (POST .../offers) ausgefuellt wurde - die Pipeline-
    Kennzahl zaehlt trotzdem den erreichten Status, nicht das (fehlende)
    Kindobjekt."""
    candidate = _create_candidate(client, "OfferViaTransitionOnly")
    company = client.post("/api/v1/clients", json={"name": "Kanzlei OfferOnly"}).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    for target in ("cv_in", "cv_out", "interview", "offer"):
        response = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition", json={"status": target}
        )
        assert response.status_code == 200, response.text

    summary = client.get(f"/api/v1/candidates/{candidate['id']}/stage-summary").json()

    assert summary["offer"] == 1
    assert summary["placement"] == 0


def test_quick_log_records_changed_by_on_the_resulting_status_change(
    client: TestClient,
) -> None:
    """Regressionsschutz (Nutzer-Feedback "Änderungshistorie...", Punkt 4):
    quick-log trieb den Prozess bisher intern per transition() voran, OHNE
    changed_by zu setzen."""
    from tests.conftest import TEST_USER_EMAIL

    candidate = _create_candidate(client, "QuickLogChangedBy")
    client.post(
        f"/api/v1/candidates/{candidate['id']}/quick-log",
        json={
            "stage": "cv_in",
            "feedback_type": "internal",
            "feedback_text": "Direkt bis Shortlist.",
            "received_at": "2026-07-01T09:00:00",
        },
    )

    history = client.get(f"/api/v1/candidates/{candidate['id']}/history").json()
    status_changes = [entry for entry in history if entry["action"] == "status_changed"]
    assert status_changes
    assert all(entry["changed_by"] == TEST_USER_EMAIL for entry in status_changes)


def test_feedback_with_target_status_records_changed_by(client: TestClient) -> None:
    """Regressionsschutz (Nutzer-Feedback "Änderungshistorie...", Punkt 4):
    ein per Feedback-target_status ausgeloester Statuswechsel liess
    changed_by bisher ebenfalls leer."""
    from tests.conftest import TEST_USER_EMAIL

    candidate = _create_candidate(client, "FeedbackTargetStatusChangedBy")
    submission = client.post(
        "/api/v1/submissions", json={"candidate_id": candidate["id"]}
    ).json()
    client.post(
        f"/api/v1/submissions/{submission['id']}/feedback",
        json={
            "feedback_type": "internal",
            "feedback_text": "Shortlist erreicht.",
            "received_at": "2026-07-02T09:00:00",
            "target_status": "cv_in",
        },
    )

    history = client.get(f"/api/v1/candidates/{candidate['id']}/history").json()
    status_changes = [entry for entry in history if entry["action"] == "status_changed"]
    assert status_changes
    assert all(entry["changed_by"] == TEST_USER_EMAIL for entry in status_changes)


def test_stage_summary_returns_404_for_unknown_candidate(client: TestClient) -> None:
    response = client.get(
        "/api/v1/candidates/00000000-0000-0000-0000-000000000000/stage-summary"
    )
    assert response.status_code == 404
