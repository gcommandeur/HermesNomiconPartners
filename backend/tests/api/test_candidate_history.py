"""Tests fuer GET /candidates/{id}/history (Nutzer-Feedback "Änderungshistorie
im Kandidatenprofil sichtbar machen"): kombiniert direkt am Kandidaten
geloggte Aktionen mit denen aller seiner Prozesse."""

from fastapi.testclient import TestClient


def _create_candidate(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/candidates", json={"first_name": "Anna", "last_name": "Muster"}
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestCandidateHistory:
    def test_status_change_on_a_submission_appears_in_candidate_history(
        self, client: TestClient
    ) -> None:
        candidate = _create_candidate(client)
        company = client.post(
            "/api/v1/clients", json={"name": "Kanzlei History", "status": "active"}
        ).json()
        submission = client.post(
            "/api/v1/submissions",
            json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
        ).json()
        transition = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition", json={"status": "cv_in"}
        )
        assert transition.status_code == 200, transition.text

        history = client.get(f"/api/v1/candidates/{candidate['id']}/history")

        assert history.status_code == 200, history.text
        actions = [entry["action"] for entry in history.json()]
        assert "status_changed" in actions
        status_change = next(e for e in history.json() if e["action"] == "status_changed")
        assert status_change["entity_type"] == "candidate_submission"
        assert status_change["entity_id"] == submission["id"]
        assert status_change["new_values"]["status"] == "cv_in"

    def test_history_is_empty_for_a_candidate_without_any_action(
        self, client: TestClient
    ) -> None:
        candidate = _create_candidate(client)

        response = client.get(f"/api/v1/candidates/{candidate['id']}/history")

        assert response.status_code == 200
        assert response.json() == []

    def test_history_does_not_leak_another_candidates_submission_events(
        self, client: TestClient
    ) -> None:
        candidate_a = _create_candidate(client)
        candidate_b = _create_candidate(client)
        submission_b = client.post(
            "/api/v1/submissions", json={"candidate_id": candidate_b["id"]}
        ).json()
        client.patch(
            f"/api/v1/submissions/{submission_b['id']}/transition", json={"status": "cv_in"}
        )

        response = client.get(f"/api/v1/candidates/{candidate_a['id']}/history")

        assert response.status_code == 200
        assert response.json() == []

    def test_history_returns_404_for_unknown_candidate(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/candidates/00000000-0000-0000-0000-000000000000/history"
        )
        assert response.status_code == 404

    def test_candidate_deletion_and_archive_both_appear_in_history(
        self, client: TestClient
    ) -> None:
        candidate = _create_candidate(client)
        company = client.post(
            "/api/v1/clients", json={"name": "Kanzlei Placement", "status": "active"}
        ).json()
        submission = client.post(
            "/api/v1/submissions",
            json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
        ).json()
        for target in ("cv_in", "cv_out", "interview", "offer", "placement"):
            client.patch(
                f"/api/v1/submissions/{submission['id']}/transition", json={"status": target}
            )
        client.post(f"/api/v1/submissions/{submission['id']}/archive")

        history = client.get(f"/api/v1/candidates/{candidate['id']}/history").json()

        actions = [entry["action"] for entry in history]
        assert actions.count("status_changed") == 5
        assert "archived" in actions
