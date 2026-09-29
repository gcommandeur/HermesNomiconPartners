"""API-Tests fuer GET /clients/near-candidate/{candidate_id} (Auftrag
"Kanzlei-Umkreissuche ausgehend vom Kandidaten").

Eigenstaendiger Endpunkt - KEIN Kettenauftrag mit Profil-Erzeugung/
Mailversand, siehe services/clients.py::ClientCompanyService.
list_near_candidate fuer die Begruendung."""

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


def test_returns_404_for_unknown_candidate(client: TestClient) -> None:
    response = client.get(
        "/api/v1/clients/near-candidate/00000000-0000-0000-0000-000000000000?radius_km=50"
    )
    assert response.status_code == 404, response.text


def test_candidate_without_resolvable_location_is_rejected(client: TestClient) -> None:
    candidate = _create_candidate(client, "Anna", city="Nirgendwostadt")

    response = client.get(f"/api/v1/clients/near-candidate/{candidate['id']}?radius_km=50")

    assert response.status_code == 422, response.text
    assert "PLZ" in response.json()["detail"] or "Ort" in response.json()["detail"]


def test_radius_km_is_required(client: TestClient) -> None:
    candidate = _create_candidate(client, "Anna", city="München")
    response = client.get(f"/api/v1/clients/near-candidate/{candidate['id']}")
    assert response.status_code == 422, response.text


def test_only_clients_within_radius_are_returned_and_sorted_by_distance(
    client: TestClient,
) -> None:
    candidate = _create_candidate(client, "Anna", city="München")
    nearby = _create_client_company(client, "Kanzlei Muenchen", city="München")
    far_away = _create_client_company(client, "Kanzlei Berlin", city="Berlin")

    response = client.get(f"/api/v1/clients/near-candidate/{candidate['id']}?radius_km=50")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["candidate_id"] == candidate["id"]
    assert body["radius_km"] == 50
    in_radius_ids = [item["client"]["id"] for item in body["in_radius"]]
    assert in_radius_ids == [nearby["id"]]
    assert far_away["id"] not in in_radius_ids
    # Naeheste Kanzlei zuerst - hier nur ein Treffer, aber distance_km muss
    # als Zahl >= 0 mitgeliefert werden.
    assert body["in_radius"][0]["distance_km"] >= 0


def test_results_are_sorted_by_ascending_distance(client: TestClient) -> None:
    candidate = _create_candidate(client, "Anna", city="München")
    munich = _create_client_company(client, "Kanzlei Muenchen", city="München")
    # ~456km von Muenchen (haversine_km) - liegt innerhalb eines weiten,
    # aber im API-Limit (500km) bleibenden Radius, siehe gleiches Muster in
    # test_candidates.py::TestRadiusFilter.
    cologne = _create_client_company(client, "Kanzlei Koeln", city="Köln")

    response = client.get(f"/api/v1/clients/near-candidate/{candidate['id']}?radius_km=480")

    body = response.json()
    ids_in_order = [item["client"]["id"] for item in body["in_radius"]]
    assert ids_in_order == [munich["id"], cologne["id"]]
    distances = [item["distance_km"] for item in body["in_radius"]]
    assert distances == sorted(distances)


def test_status_filter_narrows_results(client: TestClient) -> None:
    candidate = _create_candidate(client, "Anna", city="München")
    active = _create_client_company(client, "Kanzlei Aktiv", city="München", status="active")
    _create_client_company(client, "Kanzlei Prospect", city="München", status="prospect")

    response = client.get(
        f"/api/v1/clients/near-candidate/{candidate['id']}?radius_km=50&status=active"
    )

    body = response.json()
    ids = [item["client"]["id"] for item in body["in_radius"]]
    assert ids == [active["id"]]


def test_unresolvable_clients_are_listed_separately_not_dropped(client: TestClient) -> None:
    candidate = _create_candidate(client, "Anna", city="München")
    nearby = _create_client_company(client, "Kanzlei Muenchen", city="München")
    unresolvable = _create_client_company(client, "Kanzlei Nirgendwo", city="Nirgendwostadt")

    response = client.get(f"/api/v1/clients/near-candidate/{candidate['id']}?radius_km=50")

    body = response.json()
    in_radius_ids = [item["client"]["id"] for item in body["in_radius"]]
    unresolved_ids = [item["id"] for item in body["unresolved"]]
    assert in_radius_ids == [nearby["id"]]
    assert unresolved_ids == [unresolvable["id"]]


def test_zone_fallback_only_client_is_unresolved_not_a_match(client: TestClient) -> None:
    """Gleiche Praezisions-Regel wie fuer das Suchzentrum: eine Kanzlei, deren
    Koordinate nur ueber die grobe Zonen-Naeherung aufloesbar ist, zaehlt
    NICHT als Treffer, selbst wenn der Zonen-Zentroid zufaellig nah am
    Suchzentrum liegt - landet stattdessen in `unresolved`, wie ein
    Kandidat/Kanzlei ganz ohne aufloesbare Koordinaten."""
    candidate = _create_candidate(client, "Anna", city="München")
    zone_only = _create_client_company(
        client, "Kanzlei Nur-Zone", city="Nirgendwostadt", postal_code="85999"
    )

    response = client.get(f"/api/v1/clients/near-candidate/{candidate['id']}?radius_km=500")

    body = response.json()
    in_radius_ids = [item["client"]["id"] for item in body["in_radius"]]
    unresolved_ids = [item["id"] for item in body["unresolved"]]
    assert zone_only["id"] not in in_radius_ids
    assert zone_only["id"] in unresolved_ids


def test_candidate_center_via_zone_fallback_only_is_rejected(
    client: TestClient,
) -> None:
    """Regressionstest fuer den Illingen/Saar-Vorfall (Umkreissuche-
    Praezisions-Fix): ein Kandidat ohne bekannten Stadtnamen, dessen PLZ nur
    ueber die grobe PLZ_ZONE_COORDINATES-Naeherung aufloesbar ist (in dieser
    leeren Test-DB jede PLZ ohne postal_localities-Zeile), darf NICHT mehr
    als gueltiges Umkreis-Zentrum akzeptiert werden - die Zonen-Naeherung
    kann 100+ km danebenliegen (ein Punkt pro erster PLZ-Ziffer fuer ganz
    Deutschland), das war vorher faelschlich als "aufgeloest" durchgegangen.
    Frueheres Verhalten (200 + Treffer ueber den Zonen-Fallback) war genau
    der Bug, den dieser Fix behebt."""
    candidate = _create_candidate(client, "Anna", city="Nirgendwostadt", postal_code="80331")
    _create_client_company(client, "Kanzlei Muenchen", city="München")

    response = client.get(f"/api/v1/clients/near-candidate/{candidate['id']}?radius_km=50")

    assert response.status_code == 422, response.text
