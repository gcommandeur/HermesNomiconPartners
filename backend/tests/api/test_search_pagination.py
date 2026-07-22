from fastapi.testclient import TestClient


def test_candidate_search_finds_match_beyond_first_page(client: TestClient) -> None:
    """Legt mehr Kandidaten an als eine Seite (limit) fasst und sucht gezielt
    nach einem Datensatz, der alphabetisch/zeitlich NICHT auf Seite 1 waere -
    Beleg dafuer, dass die Suche serverseitig ueber den gesamten Bestand
    laeuft und nicht nur die geladene erste Seite durchsucht."""
    for index in range(12):
        client.post(
            "/api/v1/candidates",
            json={"first_name": f"Filler{index:02d}", "last_name": "Zzz"},
        )
    target = client.post(
        "/api/v1/candidates",
        json={"first_name": "Adelheid", "last_name": "Zzzz", "job_title": "Steuerfachwirtin"},
    ).json()

    # limit=5 erzwingt, dass eine reine "erste Seite"-Suche den Treffer NICHT
    # sehen wuerde, wenn nur clientseitig ueber bereits geladene Daten gefiltert wird.
    first_page = client.get("/api/v1/candidates?limit=5")
    assert target["id"] not in [item["id"] for item in first_page.json()["items"]]

    search_response = client.get("/api/v1/candidates?search=Adelheid&limit=5")
    assert search_response.status_code == 200
    body = search_response.json()
    assert body["total_count"] == 1
    assert body["items"][0]["id"] == target["id"]


def test_candidate_search_by_candidate_number(client: TestClient) -> None:
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Nummer", "last_name": "Suche", "candidate_number": "9999"},
    ).json()
    response = client.get("/api/v1/candidates?search=9999")
    ids = [item["id"] for item in response.json()["items"]]
    assert candidate["id"] in ids


def test_candidate_search_umlaut_case_insensitive(client: TestClient) -> None:
    """Deutsche Namen mit Umlaut in Grossschreibung (z.B. 'Öztürk') muessen
    unabhaengig von der Gross-/Kleinschreibung des Suchbegriffs gefunden
    werden - auch auf SQLite, wo das eingebaute LOWER() ASCII-only ist."""
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Aylin", "last_name": "Öztürk"},
    ).json()

    for term in ["öztürk", "ÖZTÜRK", "Öztürk", "özt"]:
        response = client.get(f"/api/v1/candidates?search={term}")
        ids = [item["id"] for item in response.json()["items"]]
        assert candidate["id"] in ids, f"search term {term!r} did not match Öztürk"


def test_client_search_by_name_website_city(client: TestClient) -> None:
    client_a = client.post(
        "/api/v1/clients",
        json={
            "name": "Ecovis München",
            "website": "https://ecovis-muenchen.example",
            "city": "München",
        },
    ).json()
    client.post("/api/v1/clients", json={"name": "Andere Kanzlei", "city": "Hamburg"})

    by_name = client.get("/api/v1/clients?search=Ecovis")
    assert client_a["id"] in [item["id"] for item in by_name.json()["items"]]

    by_website = client.get("/api/v1/clients?search=ecovis-muenchen")
    assert client_a["id"] in [item["id"] for item in by_website.json()["items"]]

    by_city = client.get("/api/v1/clients?search=münchen")
    assert client_a["id"] in [item["id"] for item in by_city.json()["items"]]


def test_contact_list_is_paginated_with_total_count(client: TestClient) -> None:
    company = client.post("/api/v1/clients", json={"name": "Kontakt-Kanzlei"}).json()
    for index in range(3):
        client.post(
            "/api/v1/contacts",
            json={
                "client_company_id": company["id"],
                "first_name": f"Kontakt{index}",
                "last_name": "Person",
                "email": f"kontakt{index}@example.com",
            },
        )

    response = client.get("/api/v1/contacts?limit=2")
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 3
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 0


def test_contact_search_matches_client_company_name_via_join(client: TestClient) -> None:
    company = client.post("/api/v1/clients", json={"name": "PwC Deutschland"}).json()
    other_company = client.post("/api/v1/clients", json={"name": "KPMG"}).json()
    contact_at_pwc = client.post(
        "/api/v1/contacts",
        json={
            "client_company_id": company["id"],
            "first_name": "Peter",
            "last_name": "Kontakt",
            "email": "peter@pwc.example",
        },
    ).json()
    client.post(
        "/api/v1/contacts",
        json={
            "client_company_id": other_company["id"],
            "first_name": "Karla",
            "last_name": "Andere",
            "email": "karla@kpmg.example",
        },
    )

    response = client.get("/api/v1/contacts?search=PwC")
    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["items"]]
    assert contact_at_pwc["id"] in ids
    assert len(ids) == 1
    assert body["items"][0]["client_company_name"] == "PwC Deutschland"


def test_contact_search_by_own_name_and_email(client: TestClient) -> None:
    company = client.post("/api/v1/clients", json={"name": "Kanzlei X"}).json()
    contact = client.post(
        "/api/v1/contacts",
        json={
            "client_company_id": company["id"],
            "first_name": "Sabine",
            "last_name": "Müller",
            "email": "sabine.mueller@example.com",
        },
    ).json()

    by_last_name = client.get("/api/v1/contacts?search=müller")
    assert contact["id"] in [item["id"] for item in by_last_name.json()["items"]]

    by_email = client.get("/api/v1/contacts?search=sabine.mueller")
    assert contact["id"] in [item["id"] for item in by_email.json()["items"]]


def test_candidate_sort_by_candidate_number_is_numeric_across_full_dataset(
    client: TestClient,
) -> None:
    """Sortierung muss ueber den gesamten Bestand laufen (ORDER BY), nicht
    nur ueber eine Seite - und candidate_number numerisch ("99" vor "100"),
    nicht lexikografisch."""
    numbers = ["9", "10", "2", "100"]
    ids_by_number = {}
    for number in numbers:
        candidate = client.post(
            "/api/v1/candidates",
            json={"first_name": "Sort", "last_name": f"Test{number}", "candidate_number": number},
        ).json()
        ids_by_number[number] = candidate["id"]

    response = client.get("/api/v1/candidates?sort_by=candidate_number&sort_dir=asc&limit=4")
    assert response.status_code == 200
    items = response.json()["items"]
    relevant = [item for item in items if item["candidate_number"] in numbers]
    assert [item["candidate_number"] for item in relevant] == ["2", "9", "10", "100"]

    desc_response = client.get("/api/v1/candidates?sort_by=candidate_number&sort_dir=desc&limit=4")
    desc_items = desc_response.json()["items"]
    relevant_desc = [item for item in desc_items if item["candidate_number"] in numbers]
    assert [item["candidate_number"] for item in relevant_desc] == ["100", "10", "9", "2"]


def test_candidate_sort_by_candidate_number_reaches_beyond_first_page(
    client: TestClient,
) -> None:
    """Kernbug-Nachweis: ein Datensatz, der alphabetisch/zeitlich NICHT auf
    Seite 1 waere, muss bei sort_by=candidate_number trotzdem an der
    richtigen Position ueber den gesamten Bestand erscheinen."""
    for index in range(15):
        client.post(
            "/api/v1/candidates",
            json={
                "first_name": "Filler",
                "last_name": f"Aaa{index:02d}",
                "candidate_number": f"{5000 + index}",
            },
        )
    lowest = client.post(
        "/api/v1/candidates",
        json={"first_name": "Ganz", "last_name": "Unten", "candidate_number": "1"},
    ).json()

    response = client.get("/api/v1/candidates?sort_by=candidate_number&sort_dir=asc&limit=5")
    items = response.json()["items"]
    assert items[0]["id"] == lowest["id"]


def test_candidate_sort_by_name(client: TestClient) -> None:
    client.post("/api/v1/candidates", json={"first_name": "Zora", "last_name": "SortName"})
    client.post("/api/v1/candidates", json={"first_name": "Anna", "last_name": "SortName"})

    response = client.get("/api/v1/candidates?search=SortName&sort_by=name&sort_dir=asc")
    names = [f"{item['first_name']} {item['last_name']}" for item in response.json()["items"]]
    assert names == ["Anna SortName", "Zora SortName"]


def test_client_sort_by_name_across_full_dataset(client: TestClient) -> None:
    client.post("/api/v1/clients", json={"name": "Zzz Sort Kanzlei"})
    client.post("/api/v1/clients", json={"name": "Aaa Sort Kanzlei"})

    response = client.get("/api/v1/clients?search=Sort Kanzlei&sort_by=name&sort_dir=asc")
    names = [item["name"] for item in response.json()["items"]]
    assert names == ["Aaa Sort Kanzlei", "Zzz Sort Kanzlei"]

    desc_response = client.get("/api/v1/clients?search=Sort Kanzlei&sort_by=name&sort_dir=desc")
    desc_names = [item["name"] for item in desc_response.json()["items"]]
    assert desc_names == ["Zzz Sort Kanzlei", "Aaa Sort Kanzlei"]


def test_candidate_sort_rejects_unknown_column(client: TestClient) -> None:
    response = client.get("/api/v1/candidates?sort_by=not_a_real_column")
    assert response.status_code == 422
