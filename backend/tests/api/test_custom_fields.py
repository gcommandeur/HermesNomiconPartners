"""Eigene Felder: Definitionen (nur Admin), Werte an Kandidat/Kanzlei/Kontakt, Filter."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tests.api.test_team_lead import Person, _make_user


def _admin(session_factory: sessionmaker[Session]) -> Person:
    return _make_user(session_factory, "admin@fields.example", "admin", "Admin")


def _field(client: TestClient, admin: Person, **overrides: object) -> dict:
    body = {
        "entity_type": "candidate",
        "label": "Führerschein",
        "field_type": "select",
        "options": ["B", "BE"],
        **overrides,
    }
    response = client.post("/api/v1/custom-fields", json=body, headers=admin.headers)
    assert response.status_code == 201, response.text
    return response.json()


def _candidate(client: TestClient, **overrides: object) -> dict:
    response = client.post(
        "/api/v1/candidates", json={"first_name": "Anna", "last_name": "Muster", **overrides}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_only_admin_defines_fields_but_everyone_lists_them(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _admin(session_factory)
    denied = client.post(
        "/api/v1/custom-fields",
        json={"entity_type": "candidate", "label": "X", "field_type": "text"},
    )
    assert denied.status_code == 403
    field = _field(client, admin)
    assert field["key"] == "fuehrerschein"
    listed = client.get("/api/v1/custom-fields?entity_type=candidate").json()
    assert [item["key"] for item in listed] == ["fuehrerschein"]
    assert client.get("/api/v1/custom-fields?entity_type=client").json() == []
    # Doppelter Schluessel wird abgelehnt.
    again = client.post(
        "/api/v1/custom-fields",
        json={"entity_type": "candidate", "label": "Führerschein", "field_type": "text"},
        headers=admin.headers,
    )
    assert again.status_code >= 400


def test_values_are_validated_and_replaced(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _admin(session_factory)
    _field(client, admin)
    _field(client, admin, label="Dienstwagen", field_type="boolean", options=[])
    _field(client, admin, label="Wunschgehalt", field_type="number", options=[])
    _field(client, admin, label="Startdatum", field_type="date", options=[])
    candidate = _candidate(client)

    bad_values = [
        {"fuehrerschein": "C"},  # keine Option
        {"dienstwagen": "ja"},  # kein Boolean
        {"wunschgehalt": "viel"},  # keine Zahl
        {"startdatum": "morgen"},  # kein Datum
        {"gibtsnicht": "x"},  # unbekannt
    ]
    for values in bad_values:
        response = client.patch(
            f"/api/v1/candidates/{candidate['id']}", json={"custom_fields": values}
        )
        assert response.status_code >= 400, values

    ok = client.patch(
        f"/api/v1/candidates/{candidate['id']}",
        json={
            "custom_fields": {
                "fuehrerschein": "BE",
                "dienstwagen": True,
                "wunschgehalt": 65000,
                "startdatum": "2026-11-01",
            }
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["custom_fields"]["fuehrerschein"] == "BE"

    # Ersetzen: nicht mitgeschickte Schluessel und leere Werte verschwinden.
    replaced = client.patch(
        f"/api/v1/candidates/{candidate['id']}",
        json={"custom_fields": {"fuehrerschein": "B", "dienstwagen": None}},
    )
    assert replaced.json()["custom_fields"] == {"fuehrerschein": "B"}
    # Andere Felder des Kandidaten lassen die eigenen Felder unberuehrt.
    other = client.patch(f"/api/v1/candidates/{candidate['id']}", json={"city": "Köln"})
    assert other.json()["custom_fields"] == {"fuehrerschein": "B"}


def test_deactivated_field_keeps_old_value_but_rejects_new_ones(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _admin(session_factory)
    field = _field(client, admin)
    candidate = _candidate(client, custom_fields={"fuehrerschein": "B"})
    assert candidate["custom_fields"] == {"fuehrerschein": "B"}

    off = client.patch(
        f"/api/v1/custom-fields/{field['id']}", json={"is_active": False}, headers=admin.headers
    )
    assert off.status_code == 200
    assert client.get("/api/v1/custom-fields?entity_type=candidate").json() == []
    inactive = client.get(
        "/api/v1/custom-fields?entity_type=candidate&include_inactive=true", headers=admin.headers
    ).json()
    assert len(inactive) == 1

    same = client.patch(
        f"/api/v1/candidates/{candidate['id']}", json={"custom_fields": {"fuehrerschein": "B"}}
    )
    assert same.status_code == 200
    changed = client.patch(
        f"/api/v1/candidates/{candidate['id']}", json={"custom_fields": {"fuehrerschein": "BE"}}
    )
    assert changed.status_code >= 400


def test_candidate_list_can_filter_by_custom_field(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _admin(session_factory)
    _field(client, admin)
    _field(client, admin, label="Dienstwagen", field_type="boolean", options=[])
    _candidate(client, first_name="A", custom_fields={"fuehrerschein": "B", "dienstwagen": True})
    _candidate(client, first_name="B", custom_fields={"fuehrerschein": "BE", "dienstwagen": False})
    _candidate(client, first_name="C")

    def names(query: str) -> list[str]:
        response = client.get(f"/api/v1/candidates?custom_field={query}")
        assert response.status_code == 200, response.text
        return sorted(item["first_name"] for item in response.json()["items"])

    assert names("fuehrerschein:BE") == ["B"]
    assert names("dienstwagen:true") == ["A"]
    assert names("dienstwagen:false") == ["B"]
    assert client.get("/api/v1/candidates?custom_field=gibtsnicht:x").status_code >= 400
    assert client.get("/api/v1/candidates?custom_field=ohnedoppelpunkt").status_code >= 400


def test_clients_and_contacts_have_their_own_fields(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _admin(session_factory)
    _field(
        client,
        admin,
        entity_type="client",
        label="Mandantenzahl",
        field_type="number",
        options=[],
    )
    # Ein Kandidatenfeld gilt NICHT fuer Kanzleien.
    _field(client, admin)
    ok = client.post(
        "/api/v1/clients", json={"name": "Kanzlei X", "custom_fields": {"mandantenzahl": 120}}
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["custom_fields"] == {"mandantenzahl": 120}
    wrong = client.post(
        "/api/v1/clients", json={"name": "Kanzlei Y", "custom_fields": {"fuehrerschein": "B"}}
    )
    assert wrong.status_code >= 400

    _field(client, admin, entity_type="contact", label="Geburtstag", field_type="date", options=[])
    contact = client.post(
        "/api/v1/contacts",
        json={
            "client_company_id": ok.json()["id"],
            "first_name": "Max",
            "last_name": "Chef",
            "custom_fields": {"geburtstag": "1980-05-17"},
        },
    )
    assert contact.status_code == 201, contact.text
    assert contact.json()["custom_fields"] == {"geburtstag": "1980-05-17"}


def test_anonymize_clears_custom_fields(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _admin(session_factory)
    _field(client, admin, label="Notiz", field_type="text", options=[])
    candidate = _candidate(client, custom_fields={"notiz": "privat"})
    response = client.post(f"/api/v1/candidates/{candidate['id']}/anonymize", headers=admin.headers)
    assert response.status_code == 200, response.text
    assert response.json()["custom_fields"] == {}
