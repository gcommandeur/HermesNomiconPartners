# ruff: noqa: F811
# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Zugriffsregel der Ueberlassung automatisch erzwingen (Muster: test_access_guard.py).

Jede Operation mit `assignment_id` oder `timesheet_id` im Pfad wird aus dem OpenAPI-Schema gelesen
und mit den ECHTEN IDs eines Einsatzes aufgerufen, der einem anderen Disponenten gehoert. Als
Fremder (kein Admin, nicht im Team) muss jede Operation 404 liefern; der Eigentuemer erreicht die
meisten. Eine neu vergessene `AssignmentAccess`/`TimesheetAccess` faellt hier sofort auf."""

import uuid
from datetime import date
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.staffing import StaffingPriorPeriod, StaffingTimesheet
from tests.api.test_staffing_api import (
    Crew,
    _assignment,
    _worker,
    crew,
    make_candidate,
)
from tests.api.test_staffing_billing import make_invoice
from tests.api.test_staffing_timesheets import public

ID_NAMES = ("assignment_id", "timesheet_id", "invoice_id", "prior_period_id")
METHODS = ("get", "post", "put", "patch", "delete")

# Operationen, die ABSICHTLICH nicht mit 404 antworten duerfen - nur mit Begruendung eintragen.
# Format: (METHODE, Pfad-Schablone). Vorzeiten gehoeren zum Leiharbeitnehmer und teilen dessen
# Sichtbarkeit (gemeinsamer Pool wie Kandidaten); nicht vorhanden liefert trotzdem 404. Diese
# Operationen werden fuer den Fremden nicht aufgerufen (Loeschen/Aendern waere wirksam).
ALLOWED_NON_404: dict[tuple[str, str], str] = {
    ("PATCH", "/api/v1/staffing/prior-periods/{prior_period_id}"): "Pool wie Leiharbeitnehmer",
    ("DELETE", "/api/v1/staffing/prior-periods/{prior_period_id}"): "Pool wie Leiharbeitnehmer",
}

_ = (crew, make_candidate, public)  # Fixtures (per Import registriert)


def _operations(client: TestClient) -> list[tuple[str, str, dict[str, Any]]]:
    paths: dict[str, Any] = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    found = []
    for path, item in paths.items():
        if not any("{" + name + "}" in path for name in ID_NAMES):
            continue
        for method in METHODS:
            if method in item:
                found.append((method.upper(), path, item[method]))
    return found


def _url(path: str, operation: dict[str, Any], real: dict[str, str]) -> str:
    url = path
    for parameter in operation.get("parameters", []):
        if parameter.get("in") != "path":
            continue
        name = parameter["name"]
        value = real.get(name) or str(uuid.uuid4())
        url = url.replace("{" + name + "}", value)
    return url


def _call(client: TestClient, method: str, url: str, headers: dict[str, str]) -> int:
    body = {} if method in ("POST", "PUT", "PATCH") else None
    return client.request(method, url, json=body, headers=headers).status_code


def _real_ids(
    client: TestClient, crew: Crew, make_candidate, session_factory: sessionmaker[Session]
) -> dict[str, str]:  # type: ignore[no-untyped-def]
    worker = _worker(client, crew.a, make_candidate())
    assignment = _assignment(client, crew.a, worker["id"], crew.client_id)  # Owner: A
    detail = client.get(
        f"/api/v1/staffing/assignments/{assignment['id']}", headers=crew.a.headers
    ).json()
    with session_factory() as session:
        sheet = StaffingTimesheet(
            assignment_id=uuid.UUID(assignment["id"]),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
        )
        session.add(sheet)
        period = StaffingPriorPeriod(
            worker_id=uuid.UUID(worker["id"]),
            client_company_id=uuid.UUID(crew.client_id),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 31),
        )
        session.add(period)
        session.commit()
        sheet_id = str(sheet.id)
        period_id = str(period.id)
    return {
        "assignment_id": assignment["id"],
        "item_id": detail["checklist"][0]["id"],
        "timesheet_id": sheet_id,
        "prior_period_id": period_id,
    }


def _invoice_id(client: TestClient, crew: Crew, make_candidate, public: TestClient) -> str:  # type: ignore[no-untyped-def]
    """Rechnung, angelegt von A (Owner: A)."""
    return str(make_invoice(client, crew, make_candidate, public)["id"])


def test_every_staffing_id_route_hides_foreign_assignments(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
    public: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    real = _real_ids(client, crew, make_candidate, session_factory)
    real["invoice_id"] = _invoice_id(client, crew, make_candidate, public)
    stranger, owner = crew.c, crew.a  # C ist weder A noch im Team von A
    operations = _operations(client)
    # Nicht wirkungslos: die Suche muss die bekannten Operationen finden (steigt mit neuen Routen).
    assert len(operations) >= 4, len(operations)
    paths = {path for _method, path, _op in operations}
    assert "/api/v1/staffing/invoices/{invoice_id}" in paths  # Rechnungen sind abgedeckt
    assert "/api/v1/staffing/prior-periods/{prior_period_id}" in paths  # Vorzeiten sind abgedeckt

    leaks = []
    reachable_for_owner = 0
    for method, path, operation in operations:
        url = _url(path, operation, real)
        if (method, path) not in ALLOWED_NON_404:
            status = _call(client, method, url, stranger.headers)
            if status != 404:
                leaks.append((method, path, status))
        if _call(client, method, url, owner.headers) != 404:
            reachable_for_owner += 1
    assert not leaks, f"Routen ohne Zugriffspruefung (Fremder bekommt kein 404): {leaks}"
    assert reachable_for_owner >= len(operations) // 2, reachable_for_owner


def test_nonexistent_ids_look_the_same_as_foreign_ones(client: TestClient, crew: Crew) -> None:
    ghosts = {name: str(uuid.uuid4()) for name in (*ID_NAMES, "item_id")}
    for method, path, operation in _operations(client):
        status = _call(client, method, _url(path, operation, ghosts), crew.a.headers)
        assert status == 404, (method, path, status)
