"""Bidirektionales Ort/PLZ-Matching bei der Kanzleien-Suche (Phase 4b) -
nutzt den PLZ<->Ort-Referenzdatensatz aus models/postal_locality.py, um auch
Kanzleien zu finden, bei denen nur eines der beiden Felder gepflegt ist."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.postal_locality import PostalLocality


def _seed_postal_locality(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(PostalLocality(postal_code="80331", locality="München"))
        session.add(PostalLocality(postal_code="80333", locality="München"))
        session.commit()


def test_search_by_city_finds_client_with_only_postal_code(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_postal_locality(session_factory)
    created = client.post(
        "/api/v1/clients", json={"name": "Kanzlei Nur-PLZ", "postal_code": "80331"}
    )
    assert created.status_code == 201

    response = client.get("/api/v1/clients", params={"region": "München"})

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["items"]]
    assert "Kanzlei Nur-PLZ" in names


def test_search_by_postal_code_finds_client_with_only_city(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_postal_locality(session_factory)
    created = client.post("/api/v1/clients", json={"name": "Kanzlei Nur-Ort", "city": "München"})
    assert created.status_code == 201

    response = client.get("/api/v1/clients", params={"region": "80331"})

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["items"]]
    assert "Kanzlei Nur-Ort" in names


def test_search_does_not_match_unrelated_city(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_postal_locality(session_factory)
    created = client.post("/api/v1/clients", json={"name": "Kanzlei Hamburg", "city": "Hamburg"})
    assert created.status_code == 201

    response = client.get("/api/v1/clients", params={"region": "München"})

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["items"]]
    assert "Kanzlei Hamburg" not in names
