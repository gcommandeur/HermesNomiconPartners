import base64

from fastapi.testclient import TestClient


def encoded_csv(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def test_candidate_import_preview_and_commit(client: TestClient) -> None:
    payload = {
        "filename": "candidates.csv",
        "content_base64": encoded_csv(
            "candidate_number,first_name,last_name,email\n1001,Erika,Muster,erika@example.com\n"
        ),
    }
    preview_response = client.post("/api/v1/import/candidates/preview", json=payload)
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["valid_count"] == 1
    assert preview["commit_supported"] is True

    commit_response = client.post(
        "/api/v1/import/candidates/commit",
        json={"rows": preview["rows"], "confirmed": True},
    )
    assert commit_response.status_code == 200
    assert commit_response.json()["imported"] == 1


def test_client_template_and_duplicate_preview(client: TestClient) -> None:
    template = client.get("/api/v1/import/clients/template?file_format=xlsx")
    assert template.status_code == 200
    assert template.content.startswith(b"PK")

    client.post("/api/v1/clients", json={"name": "Musterkanzlei"})
    preview = client.post(
        "/api/v1/import/clients/preview",
        json={
            "filename": "clients.csv",
            "content_base64": encoded_csv("name,status\nMusterkanzlei,active\n"),
        },
    ).json()
    assert preview["duplicate_count"] == 1


def test_client_import_merges_address_into_existing_duplicate_instead_of_skipping(
    client: TestClient,
) -> None:
    original = client.post(
        "/api/v1/clients",
        json={"name": "Merge Kanzlei", "kanzleigruppe": "MergeGruppe"},
    ).json()
    assert original["postal_code"] is None

    preview = client.post(
        "/api/v1/import/clients/preview",
        json={
            "filename": "clients.csv",
            "content_base64": encoded_csv("name,postal_code,city\nMerge Kanzlei,70173,Stuttgart\n"),
        },
    ).json()
    assert preview["duplicate_count"] == 1

    commit = client.post(
        "/api/v1/import/clients/commit",
        json={"rows": preview["rows"], "confirmed": True},
    )
    assert commit.status_code == 200, commit.text
    result = commit.json()
    assert result["merged"] == 1
    assert result["imported"] == 0

    updated = client.get(f"/api/v1/clients/{original['id']}").json()
    assert updated["postal_code"] == "70173"
    assert updated["city"] == "Stuttgart"


def test_candidate_export_contains_all_candidates_with_correct_columns(
    client: TestClient,
) -> None:
    a = client.post(
        "/api/v1/candidates",
        json={
            "candidate_number": "9001",
            "first_name": "Export",
            "last_name": "Eins",
            "city": "Berlin",
        },
    ).json()
    b = client.post(
        "/api/v1/candidates",
        json={"candidate_number": "9002", "first_name": "Export", "last_name": "Zwei"},
    ).json()

    response = client.get("/api/v1/import/candidates/export?file_format=csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"

    text = response.content.decode("utf-8-sig")
    rows = text.strip().splitlines()
    header = rows[0].split(",")
    assert header == [
        "candidate_number",
        "first_name",
        "last_name",
        "email",
        "phone",
        "job_title",
        "qualification",
        "postal_code",
        "city",
        "salary_expectation",
        "notice_period",
        "status",
    ]
    body = "\n".join(rows[1:])
    assert a["candidate_number"] in body
    assert b["candidate_number"] in body
    assert "Berlin" in body


def test_candidate_export_xlsx_format_returns_valid_workbook(client: TestClient) -> None:
    client.post(
        "/api/v1/candidates",
        json={"candidate_number": "9003", "first_name": "Export", "last_name": "Xlsx"},
    )
    response = client.get("/api/v1/import/candidates/export?file_format=xlsx")
    assert response.status_code == 200
    assert response.content.startswith(b"PK")


def test_candidate_import_commit_updates_differing_nonempty_fields_on_candidate_number_match(
    client: TestClient,
) -> None:
    """Master-Excel-Bulk-Korrektur: eine hochgeladene Zeile mit passender
    candidate_number aktualisiert nur Felder, die (a) einen Wert haben und
    (b) vom aktuellen Stand abweichen - eine leere Zelle fuer ein bereits
    gefuelltes Feld (hier: email) darf den bestehenden Wert NICHT loeschen."""
    original = client.post(
        "/api/v1/candidates",
        json={
            "candidate_number": "9101",
            "first_name": "Vorher",
            "last_name": "Nachher",
            "email": "vorher@example.com",
            "postal_code": "10115",
        },
    ).json()
    assert original["job_title"] is None

    # Zeile: postal_code echt geaendert (a), job_title neu gefuellt (a),
    # email-Spalte fehlt komplett in der Datei -> darf email nicht loeschen (b).
    preview = client.post(
        "/api/v1/import/candidates/preview",
        json={
            "filename": "master.csv",
            "content_base64": encoded_csv(
                "candidate_number,first_name,last_name,postal_code,job_title\n"
                "9101,Vorher,Nachher,50667,Steuerberaterin\n"
            ),
        },
    ).json()

    commit = client.post(
        "/api/v1/import/candidates/commit",
        json={"rows": preview["rows"], "confirmed": True},
    )
    assert commit.status_code == 200, commit.text
    result = commit.json()
    assert result["updated"] == 1
    assert result["imported"] == 0
    assert result["duplicates"] == 0

    updated = client.get(f"/api/v1/candidates/{original['id']}").json()
    assert updated["postal_code"] == "50667"
    assert updated["job_title"] == "Steuerberaterin"
    # email war in der hochgeladenen Datei nicht vorhanden -> unveraendert.
    assert updated["email"] == "vorher@example.com"


def test_candidate_import_commit_with_no_actual_changes_counts_as_duplicate(
    client: TestClient,
) -> None:
    original = client.post(
        "/api/v1/candidates",
        json={"candidate_number": "9102", "first_name": "Gleich", "last_name": "Geblieben"},
    ).json()

    preview = client.post(
        "/api/v1/import/candidates/preview",
        json={
            "filename": "master.csv",
            "content_base64": encoded_csv(
                "candidate_number,first_name,last_name\n9102,Gleich,Geblieben\n"
            ),
        },
    ).json()
    commit = client.post(
        "/api/v1/import/candidates/commit",
        json={"rows": preview["rows"], "confirmed": True},
    ).json()
    assert commit["updated"] == 0
    assert commit["duplicates"] == 1
    assert commit["imported"] == 0

    unchanged = client.get(f"/api/v1/candidates/{original['id']}").json()
    assert unchanged["first_name"] == "Gleich"


def test_candidate_import_commit_creates_new_row_without_candidate_number_match(
    client: TestClient,
) -> None:
    """Eine Zeile ohne candidate_number-Match (bzw. mit einer Nummer, die
    keinen bestehenden Kandidaten trifft) wird weiterhin ganz normal ueber
    den bisherigen Duplikat-Check/Neuanlage-Pfad behandelt."""
    preview = client.post(
        "/api/v1/import/candidates/preview",
        json={
            "filename": "master.csv",
            "content_base64": encoded_csv(
                "candidate_number,first_name,last_name\n9999,Brandneu,Kandidat\n"
            ),
        },
    ).json()
    commit = client.post(
        "/api/v1/import/candidates/commit",
        json={"rows": preview["rows"], "confirmed": True},
    ).json()
    assert commit["imported"] == 1
    assert commit["updated"] == 0

    found = client.get("/api/v1/candidates?search=Brandneu").json()
    assert any(item["candidate_number"] == "9999" for item in found["items"])


def test_group_locations_lists_other_sites_of_same_kanzleigruppe(client: TestClient) -> None:
    first = client.post(
        "/api/v1/clients",
        json={"name": "Ecovis München", "kanzleigruppe": "ECOVIS", "city": "München"},
    ).json()
    second = client.post(
        "/api/v1/clients",
        json={"name": "Ecovis Stuttgart", "kanzleigruppe": "ECOVIS", "city": "Stuttgart"},
    ).json()
    unrelated = client.post("/api/v1/clients", json={"name": "Andere Kanzlei"}).json()

    response = client.get(f"/api/v1/clients/{first['id']}/group-locations")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert second["id"] in ids
    assert first["id"] not in ids
    assert unrelated["id"] not in ids

    no_group = client.get(f"/api/v1/clients/{unrelated['id']}/group-locations")
    assert no_group.json() == []
