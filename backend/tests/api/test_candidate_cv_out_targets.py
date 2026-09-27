"""API-Tests fuer GET /candidates/{candidate_id}/cv-out-targets (Auftrag
'"CV Out"-Kampagne am Kandidaten') - Kanzleien im Umkreis des Kandidaten mit
mailingfaehigen Kontakten, siehe services/candidates.py::CandidateService.
cv_out_targets fuer die Filterlogik (nicht gesperrt, Kontakt mit E-Mail,
Consent-Check)."""

from fastapi.testclient import TestClient


def _create_candidate(
    client: TestClient, name: str, *, city: str | None = None, **overrides: object
) -> dict:
    payload: dict[str, object] = {"first_name": name, "last_name": "Test"}
    if city is not None:
        payload["city"] = city
    payload.update(overrides)
    response = client.post("/api/v1/candidates", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_client_company(
    client: TestClient, name: str, *, city: str | None = None, **overrides: object
) -> dict:
    payload: dict[str, object] = {"name": name}
    if city is not None:
        payload["city"] = city
    payload.update(overrides)
    response = client.post("/api/v1/clients", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_contact(client: TestClient, client_company_id: str, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "client_company_id": client_company_id,
        "first_name": "Max",
        "last_name": "Muster",
    }
    payload.update(overrides)
    response = client.post("/api/v1/contacts", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_blocks_without_candidate_consent(client: TestClient) -> None:
    candidate = _create_candidate(client, "Anna", city="München", consent_received=False)
    company = _create_client_company(client, "Kanzlei Muenchen", city="München")
    _create_contact(client, company["id"], email="kontakt@kanzlei.de")

    response = client.get(f"/api/v1/candidates/{candidate['id']}/cv-out-targets?radius_km=50")

    assert response.status_code == 403, response.text
    assert "Einverständnis" in response.json()["detail"]


def test_blocked_clients_are_excluded(client: TestClient) -> None:
    candidate = _create_candidate(client, "Anna", city="München", consent_received=True)
    blocked = _create_client_company(
        client, "Kanzlei Gesperrt", city="München", status="blocked"
    )
    _create_contact(client, blocked["id"], email="kontakt@gesperrt.de")

    response = client.get(f"/api/v1/candidates/{candidate['id']}/cv-out-targets?radius_km=50")

    assert response.status_code == 200, response.text
    ids = [item["id"] for item in response.json()["targets"]]
    assert blocked["id"] not in ids


def test_clients_without_emailed_contact_are_excluded(client: TestClient) -> None:
    candidate = _create_candidate(client, "Anna", city="München", consent_received=True)
    no_email_client = _create_client_company(client, "Kanzlei ohne Mail", city="München")
    _create_contact(client, no_email_client["id"], email=None)

    response = client.get(f"/api/v1/candidates/{candidate['id']}/cv-out-targets?radius_km=50")

    assert response.status_code == 200, response.text
    ids = [item["id"] for item in response.json()["targets"]]
    assert no_email_client["id"] not in ids


def test_returns_only_contacts_with_email_primary_first(client: TestClient) -> None:
    candidate = _create_candidate(client, "Anna", city="München", consent_received=True)
    company = _create_client_company(client, "Kanzlei Muenchen", city="München")
    _create_contact(client, company["id"], first_name="Ohne", last_name="Mail", email=None)
    _create_contact(
        client,
        company["id"],
        first_name="Sekundaer",
        last_name="Kontakt",
        email="sekundaer@kanzlei.de",
        is_primary=False,
    )
    primary = _create_contact(
        client,
        company["id"],
        first_name="Haupt",
        last_name="Kontakt",
        email="haupt@kanzlei.de",
        is_primary=True,
    )

    response = client.get(f"/api/v1/candidates/{candidate['id']}/cv-out-targets?radius_km=50")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["targets"]) == 1
    contacts = body["targets"][0]["contacts"]
    assert [c["email"] for c in contacts] == ["haupt@kanzlei.de", "sekundaer@kanzlei.de"]
    assert contacts[0]["id"] == primary["id"]


def test_out_of_radius_clients_are_not_returned(client: TestClient) -> None:
    candidate = _create_candidate(client, "Anna", city="München", consent_received=True)
    far_away = _create_client_company(client, "Kanzlei Berlin", city="Berlin")
    _create_contact(client, far_away["id"], email="kontakt@berlin.de")

    response = client.get(f"/api/v1/candidates/{candidate['id']}/cv-out-targets?radius_km=50")

    assert response.status_code == 200, response.text
    ids = [item["id"] for item in response.json()["targets"]]
    assert far_away["id"] not in ids
