from fastapi.testclient import TestClient


def _create_submission(client: TestClient, company_name: str = "Kanzlei Edit") -> dict:
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Edit", "last_name": "Case"},
    ).json()
    company = client.post(
        "/api/v1/clients",
        json={"name": company_name, "status": "active"},
    ).json()
    response = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    )
    assert response.status_code == 201
    submission = response.json()
    # Neue Submissions starten seit der Pitch-Stufe (siehe models/enums.py::
    # SubmissionStatus) - dieser Helper simuliert weiterhin einen Prozess,
    # der die Quali-Call-Stufe bereits erreicht hat.
    return _transition(client, submission["id"], "qualification_call")


def _transition(client: TestClient, submission_id: str, status: str, **extra: object) -> dict:
    response = client.patch(
        f"/api/v1/submissions/{submission_id}/transition",
        json={"status": status, **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_feedback_can_be_updated_and_deleted(client: TestClient) -> None:
    submission = _create_submission(client)
    created = client.post(
        f"/api/v1/submissions/{submission['id']}/feedback",
        json={
            "feedback_type": "internal",
            "feedback_text": "Erste Notiz",
            "received_at": "2026-06-01T10:00:00",
        },
    ).json()["feedback"]

    updated = client.patch(
        f"/api/v1/submissions/{submission['id']}/feedback/{created['id']}",
        json={"feedback_text": "Aktualisierte Notiz"},
    )
    assert updated.status_code == 200
    assert updated.json()["feedback_text"] == "Aktualisierte Notiz"
    # Unveraendert gebliebene Felder bleiben erhalten (exclude_unset).
    assert updated.json()["feedback_type"] == "internal"

    deleted = client.delete(
        f"/api/v1/submissions/{submission['id']}/feedback/{created['id']}"
    )
    assert deleted.status_code == 204
    remaining = client.get(f"/api/v1/submissions/{submission['id']}/feedback").json()
    assert remaining == []


def test_feedback_update_rejects_mismatched_submission(client: TestClient) -> None:
    submission_a = _create_submission(client, "Kanzlei A")
    submission_b = _create_submission(client, "Kanzlei B")
    feedback = client.post(
        f"/api/v1/submissions/{submission_a['id']}/feedback",
        json={
            "feedback_type": "internal",
            "feedback_text": "Nur fuer A",
            "received_at": "2026-06-01T10:00:00",
        },
    ).json()["feedback"]

    response = client.patch(
        f"/api/v1/submissions/{submission_b['id']}/feedback/{feedback['id']}",
        json={"feedback_text": "Sollte fehlschlagen"},
    )
    assert response.status_code == 404


def test_offer_can_be_updated_and_deleted(client: TestClient) -> None:
    submission = _create_submission(client)
    _transition(client, submission["id"], "cv_in")
    _transition(client, submission["id"], "cv_out")
    _transition(client, submission["id"], "interview")
    _transition(client, submission["id"], "offer")

    created = client.post(
        f"/api/v1/submissions/{submission['id']}/offers",
        json={"offered_salary": "65000.00", "offer_status": "received"},
    ).json()

    updated = client.patch(
        f"/api/v1/submissions/{submission['id']}/offers/{created['id']}",
        json={"offer_status": "accepted", "offered_salary": "68000.00"},
    )
    assert updated.status_code == 200
    assert updated.json()["offer_status"] == "accepted"
    assert updated.json()["offered_salary"] == "68000.00"

    deleted = client.delete(
        f"/api/v1/submissions/{submission['id']}/offers/{created['id']}"
    )
    assert deleted.status_code == 204
    remaining = client.get(f"/api/v1/submissions/{submission['id']}/offers").json()
    assert remaining == []


def test_placement_can_be_updated_and_deleted_with_recalculated_fee(
    client: TestClient,
) -> None:
    submission = _create_submission(client)
    _transition(client, submission["id"], "cv_in")
    _transition(client, submission["id"], "cv_out")
    _transition(client, submission["id"], "interview")
    _transition(client, submission["id"], "offer")
    _transition(client, submission["id"], "placement")

    created = client.post(
        f"/api/v1/submissions/{submission['id']}/placement",
        json={
            "start_date": "2026-09-01",
            "final_salary": "70000.00",
            "fee_percentage": "27.00",
        },
    ).json()
    assert created["calculated_fee"] == "18900.00"

    updated = client.patch(
        f"/api/v1/submissions/{submission['id']}/placement",
        json={"final_salary": "80000.00"},
    )
    assert updated.status_code == 200
    # calculated_fee wird mit dem bestehenden fee_percentage (27%) neu berechnet.
    assert updated.json()["final_salary"] == "80000.00"
    assert updated.json()["calculated_fee"] == "21600.00"

    deleted = client.delete(f"/api/v1/submissions/{submission['id']}/placement")
    assert deleted.status_code == 204
    missing = client.get(f"/api/v1/submissions/{submission['id']}/placement")
    assert missing.status_code == 404


def test_placement_update_without_placement_returns_404(client: TestClient) -> None:
    submission = _create_submission(client)
    response = client.patch(
        f"/api/v1/submissions/{submission['id']}/placement",
        json={"final_salary": "50000.00"},
    )
    assert response.status_code == 404
