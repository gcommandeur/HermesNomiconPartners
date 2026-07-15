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
