"""Tests fuer POST /submissions/{id}/archive und /unarchive (Konsolidierter
Auftrag "Prozesse abschliessen..."): expliziter Abschluss NACH einem
Placement, blendet den Prozess aus dem Kanban aus, ohne Status/Historie
anzutasten - siehe services/submissions.py::CandidateSubmissionService."""

from fastapi.testclient import TestClient


def _create_submission(client: TestClient, company_name: str = "Kanzlei Alpha") -> dict:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Test", "last_name": "Candidate"}
    ).json()
    company = client.post(
        "/api/v1/clients", json={"name": company_name, "status": "active"}
    ).json()
    response = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _transition(client: TestClient, submission_id: str, status: str, **extra: object) -> dict:
    response = client.patch(
        f"/api/v1/submissions/{submission_id}/transition",
        json={"status": status, **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_placement_submission(client: TestClient) -> dict:
    submission = _create_submission(client)
    for status in ("cv_in", "cv_out", "interview", "offer", "placement"):
        _transition(client, submission["id"], status)
    return client.get(f"/api/v1/submissions/{submission['id']}").json()


class TestArchive:
    def test_archiving_a_placement_sets_archived_at(self, client: TestClient) -> None:
        submission = _create_placement_submission(client)
        assert submission["archived_at"] is None

        response = client.post(f"/api/v1/submissions/{submission['id']}/archive")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["archived_at"] is not None
        # Status/Historie bleiben unangetastet - nur archived_at aendert sich.
        assert body["status"] == "placement"

    def test_archiving_a_non_placement_process_is_rejected(self, client: TestClient) -> None:
        submission = _create_submission(client)
        _transition(client, submission["id"], "cv_in")

        response = client.post(f"/api/v1/submissions/{submission['id']}/archive")

        assert response.status_code == 422, response.text
        assert "placement" in response.json()["detail"].lower()

    def test_archiving_twice_is_idempotent(self, client: TestClient) -> None:
        submission = _create_placement_submission(client)

        first = client.post(f"/api/v1/submissions/{submission['id']}/archive").json()
        second = client.post(f"/api/v1/submissions/{submission['id']}/archive").json()

        assert first["archived_at"] == second["archived_at"]

    def test_unarchive_clears_archived_at(self, client: TestClient) -> None:
        submission = _create_placement_submission(client)
        client.post(f"/api/v1/submissions/{submission['id']}/archive")

        response = client.post(f"/api/v1/submissions/{submission['id']}/unarchive")

        assert response.status_code == 200, response.text
        assert response.json()["archived_at"] is None

    def test_archived_submission_still_appears_in_the_plain_list(
        self, client: TestClient
    ) -> None:
        """Kein Loeschen, keine Filterung auf Backend-Ebene - GET /submissions
        liefert den Prozess weiterhin (Auswertungen/Gewaehrleistung/KPIs
        duerfen ihn sehen), nur das Kanban blendet ihn client-seitig aus."""
        submission = _create_placement_submission(client)
        client.post(f"/api/v1/submissions/{submission['id']}/archive")

        response = client.get(f"/api/v1/submissions/{submission['id']}")

        assert response.status_code == 200
        assert response.json()["id"] == submission["id"]
