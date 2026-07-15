from fastapi.testclient import TestClient


def test_mailing_group_create_and_list(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mailing-groups",
        json={
            "name": "Testgruppe A",
            "recipients": [
                {
                    "kind": "candidate",
                    "id": "c-1",
                    "name": "Max Mustermann",
                    "email": "max@example.com",
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    group = response.json()
    assert group["name"] == "Testgruppe A"
    assert len(group["recipients"]) == 1

    listed = client.get("/api/v1/mailing-groups").json()
    assert any(item["id"] == group["id"] for item in listed)


def test_mailing_group_merge_dedupes_by_email(client: TestClient) -> None:
    group_a = client.post(
        "/api/v1/mailing-groups",
        json={
            "name": "Gruppe A",
            "recipients": [
                {
                    "kind": "candidate",
                    "id": "c-1",
                    "name": "Max Mustermann",
                    "email": "max@example.com",
                },
                {
                    "kind": "candidate",
                    "id": "c-2",
                    "name": "Erika Musterfrau",
                    "email": "erika@example.com",
                },
            ],
        },
    ).json()
    group_b = client.post(
        "/api/v1/mailing-groups",
        json={
            "name": "Gruppe B",
            "recipients": [
                # Gleiche E-Mail wie Max in Gruppe A, aber andere ID -> muss dedupliziert werden.
                {
                    "kind": "candidate",
                    "id": "c-1-dup",
                    "name": "Max M.",
                    "email": "max@example.com",
                },
                {"kind": "client", "id": "cl-1", "name": "ACME GmbH", "email": "info@acme.example"},
            ],
        },
    ).json()

    merge_response = client.post(
        "/api/v1/mailing-groups/merge",
        json={
            "group_ids": [group_a["id"], group_b["id"]],
            "target_name": "Zusammengefuehrt",
        },
    )
    assert merge_response.status_code == 200, merge_response.text
    merged = merge_response.json()
    assert merged["name"] == "Zusammengefuehrt"
    emails = sorted(r["email"] for r in merged["recipients"])
    assert emails == ["erika@example.com", "info@acme.example", "max@example.com"]


def test_mailing_group_merge_can_overwrite_existing_group(client: TestClient) -> None:
    group_a = client.post(
        "/api/v1/mailing-groups",
        json={
            "name": "Overwrite Quelle A",
            "recipients": [
                {
                    "kind": "contact",
                    "id": "ct-1",
                    "name": "Ansprechpartner",
                    "email": "ap@example.com",
                }
            ],
        },
    ).json()
    target = client.post(
        "/api/v1/mailing-groups",
        json={"name": "Overwrite Ziel", "recipients": []},
    ).json()

    merge_response = client.post(
        "/api/v1/mailing-groups/merge",
        json={
            "group_ids": [group_a["id"]],
            "target_name": "Overwrite Ziel Neu",
            "overwrite_group_id": target["id"],
        },
    )
    assert merge_response.status_code == 200, merge_response.text
    merged = merge_response.json()
    assert merged["id"] == target["id"]
    assert merged["name"] == "Overwrite Ziel Neu"
    assert len(merged["recipients"]) == 1


def test_mailing_group_update_and_delete(client: TestClient) -> None:
    group = client.post(
        "/api/v1/mailing-groups", json={"name": "Loeschbar", "recipients": []}
    ).json()

    updated = client.patch(
        f"/api/v1/mailing-groups/{group['id']}", json={"template_key": "candidate_submission"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["template_key"] == "candidate_submission"

    deleted = client.delete(f"/api/v1/mailing-groups/{group['id']}")
    assert deleted.status_code == 204

    listed = client.get("/api/v1/mailing-groups").json()
    assert not any(item["id"] == group["id"] for item in listed)
