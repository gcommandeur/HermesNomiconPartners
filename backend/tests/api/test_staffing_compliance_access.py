# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Compliance (Erlaubnis, Fristen-Einstellungen, Uebernahme-Staffel) nur fuer Admins und Teamleiter:
fuer alle anderen 404 wie im Rechtemodell. Schreiben bleibt Admin-Sache (Teamleiter: 403)."""

from fastapi.testclient import TestClient

from tests.api.test_staffing_api import Crew, P, crew, make_candidate

_ = (crew, make_candidate)  # Fixtures (per Import registriert)

READS = ("/settings", "/licenses", "/takeover-fee-tiers")
LICENCE = {"authority": "BA", "valid_from": "2026-01-01"}
TIERS = {"tiers": [{"up_to_months": None, "percent_of_fee": "10"}]}


def test_member_gets_404_on_every_compliance_endpoint(client: TestClient, crew: Crew) -> None:
    who = crew.a.headers  # Mitarbeiter
    for path in READS:
        assert client.get(f"{P}{path}", headers=who).status_code == 404, path
    current = client.get(f"{P}/settings", headers=crew.admin.headers).json()
    body = {k: v for k, v in current.items() if k != "notice"}
    assert client.put(f"{P}/settings", json=body, headers=who).status_code == 404
    assert client.post(f"{P}/licenses", json=LICENCE, headers=who).status_code == 404
    assert client.put(f"{P}/takeover-fee-tiers", json=TIERS, headers=who).status_code == 404
    created = client.post(f"{P}/licenses", json=LICENCE, headers=crew.admin.headers).json()
    assert (
        client.patch(f"{P}/licenses/{created['id']}", json={"notes": "x"}, headers=who).status_code
        == 404
    )


def test_team_lead_and_admin_see_everything_but_only_admin_writes(
    client: TestClient, crew: Crew
) -> None:
    for who in (crew.b, crew.c, crew.admin):  # beide Teamleiter und der Admin
        for path in READS:
            assert client.get(f"{P}{path}", headers=who.headers).status_code == 200, path
    current = client.get(f"{P}/settings", headers=crew.b.headers).json()
    body = {k: v for k, v in current.items() if k != "notice"}
    assert client.put(f"{P}/settings", json=body, headers=crew.b.headers).status_code == 403
    assert client.post(f"{P}/licenses", json=LICENCE, headers=crew.b.headers).status_code == 403
    assert (
        client.put(f"{P}/takeover-fee-tiers", json=TIERS, headers=crew.b.headers).status_code == 403
    )
    assert client.put(f"{P}/settings", json=body, headers=crew.admin.headers).status_code == 200


def test_the_rest_of_the_staffing_view_stays_open_for_members(
    client: TestClient, crew: Crew
) -> None:
    for path in ("/overview", "/deadlines", "/tasks", "/assignments", "/workers", "/contracts"):
        assert client.get(f"{P}{path}", headers=crew.a.headers).status_code == 200, path
