from fastapi.testclient import TestClient


def _create_candidate(client: TestClient, **overrides: object) -> dict:
    payload = {
        "first_name": "Erika",
        "last_name": "Muster",
        "job_title": "Steuerberaterin",
        "qualification": "Steuerberaterin",
        "city": "München",
        "postal_code": "80331",
    }
    payload.update(overrides)
    response = client.post("/api/v1/candidates", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_vacancy(client: TestClient, **overrides: object) -> dict:
    payload = {
        "title": "Steuerberater",
        "location": "80331 München",
        "search_radius_km": 50,
        "qualifications": "Steuerberater",
    }
    payload.update(overrides)
    response = client.post("/api/v1/vacancies", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_matching_ranks_role_and_region_over_generic_overlap(client: TestClient) -> None:
    vacancy = _create_vacancy(client)
    same_role_and_region = _create_candidate(
        client, last_name="NahUndPassend", job_title="Steuerberater",
    )
    generic_overlap_only = _create_candidate(
        client, last_name="NurToken", job_title="Buchhalter", qualification="Steuerberater",
    )

    response = client.get(f"/api/v1/vacancies/{vacancy['id']}/matches")
    assert response.status_code == 200
    matches = response.json()
    ids = [match["candidate"]["id"] for match in matches]
    assert same_role_and_region["id"] in ids
    assert generic_overlap_only["id"] in ids

    strong = next(m for m in matches if m["candidate"]["id"] == same_role_and_region["id"])
    weak = next(m for m in matches if m["candidate"]["id"] == generic_overlap_only["id"])
    assert strong["score"] > weak["score"]
    assert any("Rolle" in reason for reason in strong["reasons"])
    assert strong["in_radius"] is True


def test_matching_excludes_candidates_outside_search_radius(client: TestClient) -> None:
    vacancy = _create_vacancy(client, search_radius_km=50)
    nearby = _create_candidate(client, last_name="Nah", city="München", postal_code="80331")
    far_away = _create_candidate(
        client, last_name="Fern", job_title="Steuerberater", city="Hamburg", postal_code="20095",
    )

    response = client.get(f"/api/v1/vacancies/{vacancy['id']}/matches")
    assert response.status_code == 200
    ids = [match["candidate"]["id"] for match in response.json()]
    assert nearby["id"] in ids
    assert far_away["id"] not in ids


def test_matching_excludes_blocked_and_archived_candidates(client: TestClient) -> None:
    vacancy = _create_vacancy(client)
    blocked = _create_candidate(client, last_name="Gesperrt", status="blocked")
    archived = _create_candidate(client, last_name="Archiviert", status="archived")

    response = client.get(f"/api/v1/vacancies/{vacancy['id']}/matches")
    assert response.status_code == 200
    ids = [match["candidate"]["id"] for match in response.json()]
    assert blocked["id"] not in ids
    assert archived["id"] not in ids


def test_matching_keeps_candidate_with_unresolvable_location(client: TestClient) -> None:
    vacancy = _create_vacancy(client)
    unresolvable = _create_candidate(
        client, last_name="OrtUnbekannt", city="Nirgendwostadt", postal_code=None,
    )

    response = client.get(f"/api/v1/vacancies/{vacancy['id']}/matches")
    assert response.status_code == 200
    matches = {m["candidate"]["id"]: m for m in response.json()}
    assert unresolvable["id"] in matches
    assert matches[unresolvable["id"]]["in_radius"] is None
