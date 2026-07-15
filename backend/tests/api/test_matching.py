from fastapi.testclient import TestClient


def _create_candidate(client: TestClient, **overrides: object) -> dict:
    payload = {
        "first_name": "Erika",
        "last_name": "Muster",
        "job_title": "Steuerberaterin",
        "qualification": "Steuerrecht Insolvenzrecht",
        "city": "München",
        "postal_code": "80331",
    }
    payload.update(overrides)
    response = client.post("/api/v1/candidates", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_client_company(client: TestClient, **overrides: object) -> dict:
    payload = {"name": "Kanzlei Default", "status": "active"}
    payload.update(overrides)
    response = client.post("/api/v1/clients", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_matches_rank_focus_and_location_overlap_higher(client: TestClient) -> None:
    candidate = _create_candidate(client)
    strong = _create_client_company(
        client,
        name="Kanzlei Steuerrecht München",
        focus="Steuerrecht",
        city="München",
        postal_code="80333",
    )
    weak = _create_client_company(
        client,
        name="Kanzlei Arbeitsrecht Hamburg",
        focus="Arbeitsrecht",
        city="Hamburg",
        postal_code="20095",
    )
    blocked = _create_client_company(
        client,
        name="Kanzlei Gesperrt",
        focus="Steuerrecht",
        city="München",
        status="blocked",
    )

    response = client.get(f"/api/v1/candidates/{candidate['id']}/matches")
    assert response.status_code == 200
    matches = response.json()
    ids = [match["client"]["id"] for match in matches]

    assert strong["id"] in ids
    assert weak["id"] in ids
    assert blocked["id"] not in ids

    strong_match = next(m for m in matches if m["client"]["id"] == strong["id"])
    weak_match = next(m for m in matches if m["client"]["id"] == weak["id"])
    assert strong_match["score"] > weak_match["score"]
    assert strong_match["already_submitted"] is False


def test_bulk_submit_creates_cv_out_submissions_for_all_targets(client: TestClient) -> None:
    candidate = _create_candidate(client)
    kanzlei_a = _create_client_company(client, name="Kanzlei A")
    kanzlei_b = _create_client_company(client, name="Kanzlei B")

    response = client.post(
        f"/api/v1/candidates/{candidate['id']}/bulk-submit",
        json={"client_company_ids": [kanzlei_a["id"], kanzlei_b["id"]]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_count"] == 2
    assert body["skipped_count"] == 0
    assert {item["outcome"] for item in body["results"]} == {"created"}

    submissions = client.get(f"/api/v1/candidates/{candidate['id']}/submissions").json()
    assert len(submissions) == 2
    statuses = {submission["status"] for submission in submissions}
    assert statuses == {"cv_out"}
    for submission in submissions:
        assert submission["submitted_at"] is not None

    matches = client.get(f"/api/v1/candidates/{candidate['id']}/matches").json()
    assert all(match["already_submitted"] for match in matches)


def test_bulk_submit_skips_duplicates_without_failing_the_batch(client: TestClient) -> None:
    candidate = _create_candidate(client)
    kanzlei_a = _create_client_company(client, name="Kanzlei A")
    kanzlei_b = _create_client_company(client, name="Kanzlei B")

    client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": kanzlei_a["id"]},
    )

    response = client.post(
        f"/api/v1/candidates/{candidate['id']}/bulk-submit",
        json={"client_company_ids": [kanzlei_a["id"], kanzlei_b["id"]]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_count"] == 1
    assert body["skipped_count"] == 1
    outcomes = {item["client_company_id"]: item["outcome"] for item in body["results"]}
    assert outcomes[kanzlei_a["id"]] == "skipped"
    assert outcomes[kanzlei_b["id"]] == "created"


def test_bulk_submit_rejects_interview_as_target(client: TestClient) -> None:
    candidate = _create_candidate(client)
    kanzlei = _create_client_company(client, name="Kanzlei A")

    response = client.post(
        f"/api/v1/candidates/{candidate['id']}/bulk-submit",
        json={"client_company_ids": [kanzlei["id"]], "target_status": "interview"},
    )
    assert response.status_code == 422
    assert "bulk" in response.json()["detail"].lower()
