# ruff: noqa: F811
# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Abrechnung (Rechnung aus freigegebenen Stundenzetteln mit Freigabe-Inbox), Export fuer die
Lohnabrechnung und Uebernahme durch den Kunden."""

import csv
import io
import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.staffing import StaffingInvoiceLine
from tests.api.test_staffing_api import (
    Crew,
    _assignment,
    _complete_checklist,
    _license,
    _worker,
    crew,
    make_candidate,
)
from tests.api.test_staffing_timesheets import (
    MONTH_END,
    MONTH_START,
    PUBLIC,
    START,
    _entries,
    _sheet,
    public,
)

P = "/api/v1/staffing"
TODAY = date.today()

_ = (crew, make_candidate, public)  # Fixtures (per Import registriert)


def new_client(session_factory: sessionmaker[Session], name: str) -> str:
    with session_factory() as session:
        company = ClientCompany(name=name)
        session.add(company)
        session.commit()
        return str(company.id)


def approved_sheet(  # type: ignore[no-untyped-def]
    client: TestClient,
    crew: Crew,
    make_candidate,
    public: TestClient,
    *,
    who=None,
    client_id: str | None = None,
    days: int = 3,
    hours: str = "8.00",
    rate: str | None = "28.50",
    candidate_id: str | None = None,
) -> tuple[dict, dict]:
    """Aktiver Einsatz (Owner `who`, Standard A) mit vom Kunden freigegebenem Stundenzettel;
    der Admin setzt den Verrechnungssatz."""
    who = who or crew.a
    if not client.get(f"{P}/licenses", headers=crew.admin.headers).json():
        _license(client, crew)
    worker = _worker(client, who, candidate_id or make_candidate())
    assignment = _assignment(
        client, who, worker["id"], client_id or crew.client_id, start_date=START.isoformat()
    )
    _complete_checklist(client, who, assignment["id"])
    active = client.post(
        f"{P}/assignments/{assignment['id']}/status", json={"status": "active"}, headers=who.headers
    )
    assert active.status_code == 200, active.text
    if rate is not None:
        done = client.patch(
            f"{P}/assignments/{assignment['id']}",
            json={"billing_rate": rate},
            headers=crew.admin.headers,
        )
        assert done.status_code == 200, done.text
    sheet = _sheet(client, who, assignment["id"])
    client.put(
        f"{P}/timesheets/{sheet['id']}/entries", json=_entries(days, hours), headers=who.headers
    )
    submit = client.post(f"{P}/timesheets/{sheet['id']}/submit", headers=who.headers).json()
    token = submit["approval_path"].removeprefix("/stundenzettel/")
    approved = public.post(f"{PUBLIC}/{token}/approve", json={"approver_name": "Petra Kunde"})
    assert approved.status_code == 200, approved.text
    return assignment, sheet


def draft(client: TestClient, who, *sheet_ids: str, **extra):  # type: ignore[no-untyped-def]
    return client.post(
        f"{P}/invoices", json={"timesheet_ids": list(sheet_ids), **extra}, headers=who.headers
    )


def make_invoice(client: TestClient, crew: Crew, make_candidate, public: TestClient) -> dict:  # type: ignore[no-untyped-def]
    _assignment_, sheet = approved_sheet(client, crew, make_candidate, public)
    created = draft(client, crew.a, sheet["id"])
    assert created.status_code == 201, created.text
    return created.json()


# --- Rechnung ----------------------------------------------------------------------------------


def test_draft_amounts_are_computed_but_hidden_from_non_admins(
    client: TestClient, crew: Crew, make_candidate, public: TestClient
) -> None:  # type: ignore[no-untyped-def]
    _a, sheet = approved_sheet(client, crew, make_candidate, public)  # 3 Tage x 8 Std. x 28,50 EUR
    billable = client.get(f"{P}/billable-timesheets", headers=crew.a.headers).json()
    assert [b["timesheet_id"] for b in billable] == [sheet["id"]]
    assert billable[0]["has_rate"] is True and billable[0]["total_hours"] == "24.00"
    assert "28.5" not in str(billable)  # der Satz selbst bleibt verborgen

    created = draft(client, crew.a, sheet["id"], notes="Oktober")
    assert created.status_code == 201, created.text
    invoice = created.json()
    assert invoice["invoice_status"] == "draft"
    assert invoice["amount_net"] is None and invoice["amount_gross"] is None  # Nicht-Admin
    assert all(line["rate"] is None and line["amount_net"] is None for line in invoice["lines"])
    assert invoice["lines"][0]["hours"] == "24.00"

    seen = client.get(f"{P}/invoices/{invoice['id']}", headers=crew.admin.headers).json()
    assert seen["amount_net"] == "684.00"  # 24 x 28,50
    assert seen["vat_rate"] == "19.00" and seen["amount_gross"] == "813.96"
    assert seen["lines"][0]["rate"] == "28.50" and seen["lines"][0]["amount_net"] == "684.00"
    assert seen["period_start"] == MONTH_START.isoformat()
    assert seen["period_end"] == MONTH_END.isoformat()
    # Der Zettel ist jetzt abgerechnet - kein zweites Mal
    assert client.get(f"{P}/billable-timesheets", headers=crew.a.headers).json() == []
    assert draft(client, crew.a, sheet["id"]).status_code == 409


def test_draft_rules(
    client: TestClient,
    crew: Crew,
    make_candidate,
    public: TestClient,
    session_factory: sessionmaker[Session],
) -> None:  # type: ignore[no-untyped-def]
    # ohne Verrechnungssatz
    _a, no_rate = approved_sheet(client, crew, make_candidate, public, rate=None)
    refused = draft(client, crew.a, no_rate["id"])
    assert refused.status_code == 422 and "Verrechnungssatz" in refused.json()["detail"]
    billable = client.get(f"{P}/billable-timesheets", headers=crew.a.headers).json()
    assert billable[0]["has_rate"] is False

    # nur angelegt, nicht vom Kunden freigegeben
    worker = _worker(client, crew.a, make_candidate())
    assignment = _assignment(
        client, crew.a, worker["id"], crew.client_id, start_date=START.isoformat()
    )
    _complete_checklist(client, crew.a, assignment["id"])
    client.post(
        f"{P}/assignments/{assignment['id']}/status",
        json={"status": "active"},
        headers=crew.a.headers,
    )
    client.patch(
        f"{P}/assignments/{assignment['id']}",
        json={"billing_rate": "30"},
        headers=crew.admin.headers,
    )
    unapproved = _sheet(client, crew.a, assignment["id"])
    assert draft(client, crew.a, unapproved["id"]).status_code == 422

    # zwei Kunden in einer Rechnung
    _x, first = approved_sheet(client, crew, make_candidate, public)
    other_client = new_client(session_factory, "Andere Kunde AG")
    _y, second = approved_sheet(client, crew, make_candidate, public, client_id=other_client)
    mixed = draft(client, crew.admin, first["id"], second["id"])
    assert mixed.status_code == 422 and "eines Kunden" in mixed.json()["detail"]
    # Unbekannte ID = wie fremd
    assert draft(client, crew.a, str(uuid.uuid4())).status_code == 404


def test_issue_goes_through_the_approval_inbox_for_non_admins(
    client: TestClient, crew: Crew, make_candidate, public: TestClient
) -> None:  # type: ignore[no-untyped-def]
    invoice = make_invoice(client, crew, make_candidate, public)
    url = f"{P}/invoices/{invoice['id']}"
    requested = client.post(
        f"{url}/status", json={"invoice_status": "issued"}, headers=crew.a.headers
    )
    assert requested.status_code == 200, requested.text
    result = requested.json()
    assert result["approval_request"]["status"] == "pending"
    assert result["invoice"]["invoice_status"] == "draft"  # wirkt erst nach der Freigabe
    assert result["invoice"]["approval_pending"] is True
    assert result["invoice"]["amount_net"] is None

    inbox = client.get("/api/v1/approval-requests", headers=crew.admin.headers).json()
    entry = next(r for r in inbox if r["entity_id"] == invoice["id"])
    assert (entry["kind"], entry["entity_type"]) == ("invoice_issue", "staffing_invoice")
    assert "Ueberlassungsrechnung" in entry["entity_label"] and "684.00" in entry["entity_label"]
    assert entry["proposed_values"]["amount_gross"] == "813.96"

    approved = client.post(
        f"/api/v1/approval-requests/{entry['id']}/approve", headers=crew.admin.headers
    )
    assert approved.status_code == 200, approved.text
    after = client.get(url, headers=crew.a.headers).json()
    assert after["invoice_status"] == "issued"
    assert after["invoice_date"] == TODAY.isoformat()
    assert after["approval_pending"] is False
    assert after["amount_net"] is None  # Dispatcher sehen weiterhin keine Betraege
    # entschieden ist entschieden
    assert (
        client.post(
            f"/api/v1/approval-requests/{entry['id']}/approve", headers=crew.admin.headers
        ).status_code
        == 409
    )


def test_rejected_issue_request_keeps_the_draft(
    client: TestClient, crew: Crew, make_candidate, public: TestClient
) -> None:  # type: ignore[no-untyped-def]
    invoice = make_invoice(client, crew, make_candidate, public)
    url = f"{P}/invoices/{invoice['id']}"
    client.post(f"{url}/status", json={"invoice_status": "issued"}, headers=crew.a.headers)
    inbox = client.get("/api/v1/approval-requests", headers=crew.admin.headers).json()
    entry = next(r for r in inbox if r["entity_id"] == invoice["id"])
    rejected = client.post(
        f"/api/v1/approval-requests/{entry['id']}/reject",
        json={"decision_note": "Satz pruefen"},
        headers=crew.admin.headers,
    )
    assert rejected.status_code == 200
    again = client.get(url, headers=crew.a.headers).json()
    assert again["invoice_status"] == "draft" and again["approval_pending"] is False


def test_status_rules_for_admins_and_non_admins(
    client: TestClient, crew: Crew, make_candidate, public: TestClient
) -> None:  # type: ignore[no-untyped-def]
    invoice = make_invoice(client, crew, make_candidate, public)
    url = f"{P}/invoices/{invoice['id']}/status"
    # Admin stellt direkt, danach faellig und bezahlt; Rueckwaerts ist verboten
    issued = client.post(
        url,
        json={
            "invoice_status": "issued",
            "payment_due_date": (TODAY + timedelta(days=14)).isoformat(),
        },
        headers=crew.admin.headers,
    )
    assert issued.status_code == 200 and issued.json()["approval_request"] is None
    assert issued.json()["invoice"]["invoice_status"] == "issued"
    assert issued.json()["invoice"]["payment_due_date"] == (TODAY + timedelta(days=14)).isoformat()
    # Nicht-Admin darf eine gestellte Rechnung weder stornieren noch als bezahlt markieren
    for target in ("cancelled", "paid", "due"):
        assert (
            client.post(url, json={"invoice_status": target}, headers=crew.a.headers).status_code
            == 403
        ), target
    assert (
        client.post(url, json={"invoice_status": "draft"}, headers=crew.admin.headers).status_code
        == 422
    )
    assert (
        client.post(url, json={"invoice_status": "due"}, headers=crew.admin.headers).status_code
        == 200
    )
    paid = client.post(url, json={"invoice_status": "paid"}, headers=crew.admin.headers).json()
    assert paid["invoice"]["invoice_status"] == "paid" and paid["invoice"]["paid_at"] is not None
    assert (
        client.post(
            url, json={"invoice_status": "cancelled"}, headers=crew.admin.headers
        ).status_code
        == 422
    )


def test_cancelling_a_draft_frees_the_timesheets(
    client: TestClient,
    crew: Crew,
    make_candidate,
    public: TestClient,
    session_factory: sessionmaker[Session],
) -> None:  # type: ignore[no-untyped-def]
    _a, sheet = approved_sheet(client, crew, make_candidate, public)
    invoice = draft(client, crew.a, sheet["id"]).json()
    cancelled = client.post(
        f"{P}/invoices/{invoice['id']}/status",
        json={"invoice_status": "cancelled"},
        headers=crew.a.headers,
    )
    assert (
        cancelled.status_code == 200
        and cancelled.json()["invoice"]["invoice_status"] == "cancelled"
    )
    with session_factory() as session:
        line = session.scalars(select(StaffingInvoiceLine)).one()
        assert line.timesheet_id is None  # Zeile bleibt als Nachweis
    assert [
        b["timesheet_id"]
        for b in client.get(f"{P}/billable-timesheets", headers=crew.a.headers).json()
    ] == [sheet["id"]]
    assert draft(client, crew.a, sheet["id"]).status_code == 201  # wieder abrechenbar


def test_invoice_visibility_follows_the_creator_scope(
    client: TestClient, crew: Crew, make_candidate, public: TestClient
) -> None:  # type: ignore[no-untyped-def]
    invoice = make_invoice(client, crew, make_candidate, public)  # angelegt von A
    ids = lambda who: {i["id"] for i in client.get(f"{P}/invoices", headers=who.headers).json()}  # noqa: E731
    assert ids(crew.a) == {invoice["id"]}
    assert ids(crew.b) == {invoice["id"]}  # Teamleiter von A
    assert ids(crew.c) == set()
    assert ids(crew.admin) == {invoice["id"]}
    assert client.get(f"{P}/invoices/{invoice['id']}", headers=crew.c.headers).status_code == 404
    assert client.get(f"{P}/invoices/{uuid.uuid4()}", headers=crew.a.headers).status_code == 404
    # Fremde Stundenzettel (Einsatz von A) koennen C nicht abrechnen
    _x, other_sheet = approved_sheet(client, crew, make_candidate, public)
    assert draft(client, crew.c, other_sheet["id"]).status_code == 404
    assert client.get(f"{P}/billable-timesheets", headers=crew.c.headers).json() == []


# --- Export ------------------------------------------------------------------------------------


def _csv(client: TestClient, headers, start: date, end: date):  # type: ignore[no-untyped-def]
    return client.get(
        f"{P}/export/hours.csv?period_start={start.isoformat()}&period_end={end.isoformat()}",
        headers=headers,
    )


def test_hours_export_is_admin_only_and_only_counts_approved_hours(
    client: TestClient,
    crew: Crew,
    make_candidate,
    public: TestClient,
    session_factory: sessionmaker[Session],
) -> None:  # type: ignore[no-untyped-def]
    a_candidate = make_candidate("Anna")
    approved_sheet(
        client, crew, make_candidate, public, candidate_id=a_candidate, days=3, hours="7.50"
    )
    # Zweiter Zettel: nur eingereicht (nicht freigegeben) -> zaehlt nicht
    worker = _worker(client, crew.a, make_candidate("Bernd"))
    other = _assignment(client, crew.a, worker["id"], crew.client_id, start_date=START.isoformat())
    _complete_checklist(client, crew.a, other["id"])
    client.post(
        f"{P}/assignments/{other['id']}/status", json={"status": "active"}, headers=crew.a.headers
    )
    pending = _sheet(client, crew.a, other["id"])
    client.put(f"{P}/timesheets/{pending['id']}/entries", json=_entries(2), headers=crew.a.headers)
    client.post(f"{P}/timesheets/{pending['id']}/submit", headers=crew.a.headers)

    assert _csv(client, crew.a.headers, MONTH_START, MONTH_END).status_code == 403
    assert _csv(client, crew.b.headers, MONTH_START, MONTH_END).status_code == 403
    assert _csv(client, crew.admin.headers, MONTH_END, MONTH_START).status_code == 422
    response = _csv(client, crew.admin.headers, MONTH_START, MONTH_END)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"].startswith('attachment; filename="stunden_')
    assert response.content.startswith(b"\xef\xbb\xbf")  # UTF-8 mit BOM (Excel)
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert rows[0][:4] == ["Personalnummer", "Nachname", "Vorname", "Kunde"]
    assert len(rows) == 2  # Kopfzeile + genau ein Leiharbeitnehmer (nur freigegebene Stunden)
    header, row = rows[0], dict(zip(rows[0], rows[1], strict=True))
    assert row["Vorname"] == "Anna" and row["Kunde"] == "Beispiel Logistik GmbH"
    assert row["Stunden"] == "22,50" and row["Arbeitstage"] == "3" and row["Pausen Minuten"] == "90"
    assert row["Zeitraum von"] == f"{MONTH_START:%d.%m.%Y}"
    assert len(header) == 14

    # Zeitraum schneidet Tage ab: nur der erste Tag
    only_first = _csv(client, crew.admin.headers, MONTH_START, MONTH_START)
    parsed = list(csv.reader(io.StringIO(only_first.content.decode("utf-8-sig")), delimiter=";"))
    assert dict(zip(parsed[0], parsed[1], strict=True))["Stunden"] == "7,50"
    # Zeitraum ohne Stunden: nur die Kopfzeile
    empty = _csv(
        client, crew.admin.headers, TODAY - timedelta(days=500), TODAY - timedelta(days=490)
    )
    assert len(list(csv.reader(io.StringIO(empty.content.decode("utf-8-sig")), delimiter=";"))) == 1


def test_export_neutralizes_spreadsheet_formulas(
    client: TestClient,
    crew: Crew,
    make_candidate,
    public: TestClient,
    session_factory: sessionmaker[Session],
) -> None:  # type: ignore[no-untyped-def]
    candidate_id = make_candidate("Mallory")
    approved_sheet(client, crew, make_candidate, public, candidate_id=candidate_id)
    with session_factory() as session:
        candidate = session.get(Candidate, uuid.UUID(candidate_id))
        candidate.last_name = '=HYPERLINK("http://boese.example","klick")'
        session.commit()
    text = _csv(client, crew.admin.headers, MONTH_START, MONTH_END).content.decode("utf-8-sig")
    assert "'=HYPERLINK" in text
    assert ";=HYPERLINK" not in text


# --- Uebernahme --------------------------------------------------------------------------------


def test_takeover_ends_the_assignment_and_creates_a_placement_process(
    client: TestClient, crew: Crew, make_candidate, public: TestClient
) -> None:  # type: ignore[no-untyped-def]
    assignment, _sheet_ = approved_sheet(client, crew, make_candidate, public)
    url = f"{P}/assignments/{assignment['id']}/takeover"
    result = client.post(
        url, json={"annual_salary": "60000", "fee_percentage": "25"}, headers=crew.a.headers
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["assignment"]["status"] == "ended"
    assert body["assignment"]["actual_end_date"] == TODAY.isoformat()
    assert body["assignment"]["hourly_wage"] is None  # Nicht-Admin
    submission = client.get(
        f"/api/v1/submissions/{body['submission_id']}", headers=crew.a.headers
    ).json()
    assert submission["status"] == "qualification_call"
    assert submission["fee_percentage"] == "25.00" and submission["expected_fee"] == "15000.00"
    assert submission["owner_user_id"] == crew.a.id
    assert "Uebernahme" in submission["summary"]
    assert submission["salary_at_submission"] == "60000.00 EUR/Jahr"
    # Zweimal geht nicht
    assert client.post(url, json={}, headers=crew.a.headers).status_code == 422
    # Audit (Admin)
    assert "taken_over" in client.get("/api/v1/audit-logs", headers=crew.admin.headers).text


def test_takeover_uses_the_client_fee_by_default_and_refuses_duplicates(
    client: TestClient, crew: Crew, make_candidate, public: TestClient
) -> None:  # type: ignore[no-untyped-def]
    assignment, _s = approved_sheet(client, crew, make_candidate, public)
    detail = client.get(f"{P}/assignments/{assignment['id']}", headers=crew.a.headers).json()
    worker = client.get(f"{P}/workers/{detail['worker_id']}", headers=crew.a.headers).json()
    # Es gibt schon einen aktiven Prozess fuer Kandidat und Kunde -> Konflikt, Einsatz bleibt aktiv
    existing = client.post(
        "/api/v1/submissions",
        json={"candidate_id": worker["candidate_id"], "client_company_id": crew.client_id},
        headers=crew.a.headers,
    )
    assert existing.status_code == 201, existing.text
    url = f"{P}/assignments/{assignment['id']}/takeover"
    conflict = client.post(url, json={}, headers=crew.a.headers)
    assert conflict.status_code == 409
    assert (
        client.get(f"{P}/assignments/{assignment['id']}", headers=crew.a.headers).json()["status"]
        == "active"
    )
    # Nach dem Abbruch des alten Prozesses geht es; ohne Prozentsatz gilt der des Kunden (27 %)
    cancel = client.patch(
        f"/api/v1/submissions/{existing.json()['id']}/transition",
        json={"status": "cancelled", "cancellation_reason": "client_rejected"},
        headers=crew.a.headers,
    )
    assert cancel.status_code == 200, cancel.text
    ok = client.post(url, json={"annual_salary": "50000"}, headers=crew.a.headers)
    assert ok.status_code == 200, ok.text
    created = client.get(
        f"/api/v1/submissions/{ok.json()['submission_id']}", headers=crew.a.headers
    ).json()
    assert created["fee_percentage"] == "27.00" and created["expected_fee"] == "13500.00"


def test_takeover_needs_an_active_assignment(
    client: TestClient, crew: Crew, make_candidate
) -> None:  # type: ignore[no-untyped-def]
    worker = _worker(client, crew.a, make_candidate())
    planned = _assignment(client, crew.a, worker["id"], crew.client_id)
    assert (
        client.post(
            f"{P}/assignments/{planned['id']}/takeover", json={}, headers=crew.a.headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{P}/assignments/{planned['id']}/takeover", json={}, headers=crew.c.headers
        ).status_code
        == 404
    )
