"""Tests fuer zwei Placement/Fee-Punkte (Nutzer-Auftrag 2026-09-08):

1. Archivierte Placements verschwinden aus den Cockpit-Action-Listen
   (hot_processes/data_gaps), zaehlen aber weiterhin in kpis.placements -
   siehe services/operational.py::CockpitService.build().
2. Placement.rabatt_percentage/fee_fix beeinflussen calculated_fee wie
   spezifiziert - siehe services/recruiting.py::_calculate_fee()."""

from fastapi.testclient import TestClient


def _create_submission(
    client: TestClient, company_name: str = "Kanzlei Alpha", **company_extra: object
) -> dict:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Test", "last_name": "Candidate"}
    ).json()
    company = client.post(
        "/api/v1/clients", json={"name": company_name, "status": "active", **company_extra}
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


def _create_placement_submission(client: TestClient, **company_extra: object) -> dict:
    submission = _create_submission(client, **company_extra)
    for status in ("cv_in", "cv_out", "interview", "offer", "placement"):
        _transition(client, submission["id"], status)
    return client.get(f"/api/v1/submissions/{submission['id']}").json()


class TestCockpitExcludesArchivedPlacements:
    def test_archiving_removes_placement_from_hot_processes_but_keeps_kpi_count(
        self, client: TestClient
    ) -> None:
        submission = _create_placement_submission(client)
        client.post(
            f"/api/v1/submissions/{submission['id']}/placement",
            json={
                "start_date": "2026-09-01",
                "final_salary": "70000.00",
                "fee_percentage": "27.00",
            },
        )

        before = client.get("/api/v1/cockpit?period=quarter").json()
        before_ids = {item["submission_id"] for item in before["hot_processes"]}
        assert submission["id"] in before_ids
        assert before["kpis"]["placements"] == 1

        client.post(f"/api/v1/submissions/{submission['id']}/archive")

        after = client.get("/api/v1/cockpit?period=quarter").json()
        after_ids = {item["submission_id"] for item in after["hot_processes"]}
        assert submission["id"] not in after_ids
        # KPI-Zahl zaehlt archivierte Placements weiterhin - Nutzer-Vorgabe:
        # nur die Action-Listen sollen sie ausblenden, nicht die Kennzahlen.
        assert after["kpis"]["placements"] == 1

    def test_archived_data_gap_submission_is_hidden_too(self, client: TestClient) -> None:
        # Status "placement" OHNE erfassten Placement-Datensatz -> data_gaps.
        submission = _create_submission(client)
        for status in ("cv_in", "cv_out", "interview", "offer", "placement"):
            _transition(client, submission["id"], status)

        before = client.get("/api/v1/cockpit?period=quarter").json()
        before_ids = {item["submission_id"] for item in before["data_gaps"]}
        assert submission["id"] in before_ids

        # archive() erfordert normalerweise ein Placement-Objekt? Nein - der
        # Endpoint prueft nur den Submission-Status (siehe
        # services/submissions.py::archive), ein data-gap-Prozess im Status
        # "placement" ohne Placement-Datensatz laesst sich also archivieren.
        response = client.post(f"/api/v1/submissions/{submission['id']}/archive")
        assert response.status_code == 200, response.text

        after = client.get("/api/v1/cockpit?period=quarter").json()
        after_ids = {item["submission_id"] for item in after["data_gaps"]}
        assert submission["id"] not in after_ids


class TestPlacementFeeCalculation:
    def test_rabatt_percentage_reduces_calculated_fee(self, client: TestClient) -> None:
        submission = _create_placement_submission(client)

        placement = client.post(
            f"/api/v1/submissions/{submission['id']}/placement",
            json={
                "start_date": "2026-09-01",
                "final_salary": "70000.00",
                "fee_percentage": "27.00",
                "rabatt_percentage": "10.00",
            },
        )
        assert placement.status_code == 201, placement.text
        data = placement.json()
        # 70000 * 27% = 18900, minus 10% Rabatt = 17010.00
        assert data["calculated_fee"] == "17010.00"
        assert data["rabatt_percentage"] == "10.00"
        assert data["fee_fix"] is None

    def test_rabatt_percentage_defaults_to_zero(self, client: TestClient) -> None:
        submission = _create_placement_submission(client)

        placement = client.post(
            f"/api/v1/submissions/{submission['id']}/placement",
            json={
                "start_date": "2026-09-01",
                "final_salary": "70000.00",
                "fee_percentage": "27.00",
            },
        )
        assert placement.status_code == 201, placement.text
        data = placement.json()
        assert data["calculated_fee"] == "18900.00"
        assert data["rabatt_percentage"] == "0.00"

    def test_fee_fix_overrides_percentage_calculation(self, client: TestClient) -> None:
        submission = _create_placement_submission(client)

        placement = client.post(
            f"/api/v1/submissions/{submission['id']}/placement",
            json={
                "start_date": "2026-09-01",
                "final_salary": "70000.00",
                "fee_percentage": "27.00",
                "rabatt_percentage": "10.00",
                "fee_fix": "15000.00",
            },
        )
        assert placement.status_code == 201, placement.text
        data = placement.json()
        # fee_fix gewinnt, fee_percentage/rabatt_percentage bleiben
        # gespeichert (informativ), fliessen aber nicht in calculated_fee ein.
        assert data["calculated_fee"] == "15000.00"
        assert data["fee_fix"] == "15000.00"
        assert data["fee_percentage"] == "27.00"
        assert data["rabatt_percentage"] == "10.00"

    def test_update_recalculates_fee_when_switching_to_fee_fix_and_back(
        self, client: TestClient
    ) -> None:
        submission = _create_placement_submission(client)
        placement = client.post(
            f"/api/v1/submissions/{submission['id']}/placement",
            json={
                "start_date": "2026-09-01",
                "final_salary": "70000.00",
                "fee_percentage": "27.00",
            },
        ).json()
        assert placement["calculated_fee"] == "18900.00"

        switched = client.patch(
            f"/api/v1/submissions/{submission['id']}/placement",
            json={"fee_fix": "12000.00"},
        )
        assert switched.status_code == 200, switched.text
        switched_data = switched.json()
        assert switched_data["calculated_fee"] == "12000.00"
        # fee_percentage bleibt unveraendert gespeichert (ausgegraut im
        # Frontend, nicht geloescht).
        assert switched_data["fee_percentage"] == "27.00"

        back = client.patch(
            f"/api/v1/submissions/{submission['id']}/placement",
            json={"clear_fee_fix": True},
        )
        assert back.status_code == 200, back.text
        back_data = back.json()
        assert back_data["fee_fix"] is None
        # Zurueck auf "Berechnet" - Formel greift wieder mit dem weiterhin
        # gespeicherten fee_percentage.
        assert back_data["calculated_fee"] == "18900.00"

    def test_update_leaving_fee_percentage_blank_keeps_stored_value(
        self, client: TestClient
    ) -> None:
        submission = _create_placement_submission(client, fee_percentage="30.00")
        placement = client.post(
            f"/api/v1/submissions/{submission['id']}/placement",
            json={"start_date": "2026-09-01", "final_salary": "70000.00"},
        ).json()
        assert placement["fee_percentage"] == "30.00"

        updated = client.patch(
            f"/api/v1/submissions/{submission['id']}/placement",
            json={"rabatt_percentage": "5.00"},
        )
        assert updated.status_code == 200, updated.text
        data = updated.json()
        # fee_percentage nicht mitgeschickt -> unveraendert (30%), nur der
        # Rabatt wurde neu angewendet: 70000*30% = 21000, -5% = 19950.00
        assert data["fee_percentage"] == "30.00"
        assert data["calculated_fee"] == "19950.00"

    def test_average_fee_per_placement_reflects_rabatt(self, client: TestClient) -> None:
        submission = _create_placement_submission(client)
        client.post(
            f"/api/v1/submissions/{submission['id']}/placement",
            json={
                "start_date": "2026-09-01",
                "final_salary": "70000.00",
                "fee_percentage": "27.00",
                "rabatt_percentage": "10.00",
            },
        )

        cockpit = client.get("/api/v1/cockpit?period=quarter").json()
        assert cockpit["recruiting_kpis"]["average_fee_per_placement"] == 17010.0
