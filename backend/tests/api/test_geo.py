from fastapi.testclient import TestClient


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
