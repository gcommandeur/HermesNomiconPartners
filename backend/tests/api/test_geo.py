from fastapi.testclient import TestClient


def test_results_only_contains_clients_not_candidates(client: TestClient) -> None:
    """Punkt 1 des Auftrags "Geo Mapping auf reine Kanzleien-Suche
    reduzieren": /geo-mapping/results liefert nur noch Kanzleien - ein
    angelegter Kandidat darf nicht mehr in den Ergebnissen auftauchen, und
    die Zeilen haben kein `kind`-Feld mehr."""
    candidate = client.post(
        "/api/v1/candidates",
        json={
            "first_name": "Anna",
            "last_name": "Muster",
            "postal_code": "80331",
            "city": "München",
        },
    ).json()
    company = client.post(
        "/api/v1/clients",
        json={"name": "Muster Kanzlei", "postal_code": "80331", "city": "München"},
    ).json()

    response = client.get("/api/v1/geo-mapping/results")
    assert response.status_code == 200
    body = response.json()

    ids = {item["id"] for item in body}
    assert company["id"] in ids
    assert candidate["id"] not in ids
    assert all("kind" not in item for item in body)


def test_geocode_resolves_known_city(client: TestClient) -> None:
    response = client.get("/api/v1/geo-mapping/geocode", params={"query": "München"})
    assert response.status_code == 200
    body = response.json()
    assert body["latitude"] is not None
    assert body["longitude"] is not None


def test_geocode_resolves_postal_code_zone(client: TestClient) -> None:
    response = client.get("/api/v1/geo-mapping/geocode", params={"query": "80331"})
    assert response.status_code == 200
    body = response.json()
    assert body["latitude"] is not None
    assert body["longitude"] is not None


def test_geocode_resolves_plz_and_city_combined(client: TestClient) -> None:
    response = client.get("/api/v1/geo-mapping/geocode", params={"query": "80331 München"})
    assert response.status_code == 200
    body = response.json()
    assert body["latitude"] is not None
    assert body["longitude"] is not None


def test_geocode_returns_nulls_for_unknown_place(client: TestClient) -> None:
    response = client.get("/api/v1/geo-mapping/geocode", params={"query": "Nirgendwostadt"})
    assert response.status_code == 200
    body = response.json()
    assert body["latitude"] is None
    assert body["longitude"] is None
