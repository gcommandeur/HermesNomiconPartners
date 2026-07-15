from fastapi.testclient import TestClient

_company_counter = 0


def _create_submission(client: TestClient, postal_code: str = "70173") -> dict:
    global _company_counter
    _company_counter += 1
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Score", "last_name": "Case", "postal_code": postal_code},
    ).json()
    company = client.post(
        "/api/v1/clients", json={"name": f"Kanzlei Score {_company_counter}"}
    ).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    return submission


def test_closing_score_hot_status(client: TestClient) -> None:
    submission = _create_submission(client)

    response = client.patch(
        f"/api/v1/submissions/{submission['id']}/closing-score",
        json={
            "pain_staerke": 5,
            "entscheidungsklarheit": 5,
            "markt_fit": 5,
            "momentum": 5,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["closing_probability"] == 100.0
    assert data["closing_status"] == "hot"
    assert data["action_recommendation"] == "Fokus tägliche Führung"

    submission_detail = client.get(f"/api/v1/submissions/{submission['id']}").json()
    assert submission_detail["closing_status"] == "hot"
    assert submission_detail["pain_staerke"] == 5


def test_closing_score_gate_forces_stop_even_with_high_other_scores(
    client: TestClient,
) -> None:
    submission = _create_submission(client)

    response = client.patch(
        f"/api/v1/submissions/{submission['id']}/closing-score",
        json={
            "pain_staerke": 5,
            "entscheidungsklarheit": 5,
            "markt_fit": 1,
            "momentum": 5,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["closing_status"] == "stop"
    assert response.json()["action_recommendation"] == "Kein CV OUT"


def test_closing_score_without_momentum_still_computes(client: TestClient) -> None:
    submission = _create_submission(client)

    response = client.patch(
        f"/api/v1/submissions/{submission['id']}/closing-score",
        json={"pain_staerke": 3, "entscheidungsklarheit": 3, "markt_fit": 3},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    # (3+3+3+0)/20*100 = 45.0 -> below all thresholds -> stop
    assert data["closing_probability"] == 45.0
    assert data["closing_status"] == "stop"


def test_region_modifier_shifts_effective_markt_fit(client: TestClient) -> None:
    modifier = client.post(
        "/api/v1/region-modifiers",
        json={"plz_prefix": "70", "label": "Stuttgart", "modifier": 0.5},
    )
    assert modifier.status_code == 201, modifier.text

    submission = _create_submission(client, postal_code="70173")
    response = client.patch(
        f"/api/v1/submissions/{submission['id']}/closing-score",
        json={"pain_staerke": 4, "entscheidungsklarheit": 4, "markt_fit": 4, "momentum": 4},
    )
    assert response.status_code == 200, response.text
    # effektiver_markt_fit = min(5, 4+0.5) = 4.5 -> (4+4+4.5+4)/20*100 = 82.5
    assert response.json()["closing_probability"] == 82.5
    assert response.json()["closing_status"] == "hot"


def test_priority_view_orders_by_probability_times_expected_fee(client: TestClient) -> None:
    low_value = _create_submission(client)
    client.patch(
        f"/api/v1/submissions/{low_value['id']}",
        json={"expected_fee": "10000.00"},
    )
    client.patch(
        f"/api/v1/submissions/{low_value['id']}/closing-score",
        json={"pain_staerke": 3, "entscheidungsklarheit": 3, "markt_fit": 3, "momentum": 3},
    )

    high_value = _create_submission(client)
    client.patch(
        f"/api/v1/submissions/{high_value['id']}",
        json={"expected_fee": "50000.00"},
    )
    client.patch(
        f"/api/v1/submissions/{high_value['id']}/closing-score",
        json={"pain_staerke": 5, "entscheidungsklarheit": 5, "markt_fit": 5, "momentum": 5},
    )

    response = client.get("/api/v1/submissions/priority-view")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert ids[0] == high_value["id"]
    assert ids.index(high_value["id"]) < ids.index(low_value["id"])
