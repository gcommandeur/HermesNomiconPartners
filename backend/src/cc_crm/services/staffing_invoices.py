# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Rechnungen über freigegebene Stundenzettel, Freigabe ("Rechnung stellen") und CSV-Export.

Nutzt das vorhandene Rechnungs- und Freigabemodell der Vermittlung: derselbe Status
(`InvoiceStatus`, erlaubte Uebergaenge aus services/invoices.py), dieselben Betragsfelder wie `Fee`
und die Freigabe-Inbox - "Rechnung stellen" durch einen Nicht-Admin löst eine Anfrage
(`kind="invoice_issue"`, `entity_type="staffing_invoice"`) aus, die ein Admin unter /freigaben
entscheidet (services/approvals.py ruft dafuer `apply_staffing_invoice_issue`).

Beträge (Verrechnungssatz mal Stunden) sind Margendaten: Nicht-Admins sehen sie nie (die API
setzt sie auf None, siehe services/staffing_visibility.py). Sie können Entwuerfe aus
Stundenzetteln ihres Bereichs erstellen und das Stellen beantragen, ohne die Beträge zu kennen."""

import csv
import io
import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cc_crm.core.config import get_settings
from cc_crm.core.errors import (
    BusinessRuleError,
    ConflictError,
    EntityNotFoundError,
    PermissionDeniedError,
)
from cc_crm.models.approval_request import ApprovalRequest
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import InvoiceStatus
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingInvoice,
    StaffingInvoiceLine,
    StaffingTimesheet,
    StaffingTimesheetEntry,
    StaffingTimesheetStatus,
    StaffingWorker,
)
from cc_crm.models.user import User
from cc_crm.schemas.approval import InvoiceStatusChange
from cc_crm.schemas.staffing import (
    StaffingBillableTimesheetRead,
    StaffingInvoiceCreate,
    StaffingInvoiceLineRead,
    StaffingInvoiceRead,
)
from cc_crm.services import staffing_audit as audit
from cc_crm.services.approvals import ApprovalService, needs_approval
from cc_crm.services.invoices import ALLOWED_INVOICE_TRANSITIONS

ENTITY_TYPE = "staffing_invoice"  # entity_type der Freigabe-Anfrage
ENTITY_INVOICE = "staffing_invoice"  # entity_type im Audit-Log
CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _name(first: str | None, last: str | None) -> str:
    return f"{first or ''} {last or ''}".strip() or "Unbekannt"


def _as_date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def apply_status(invoice: StaffingInvoice, target: InvoiceStatus, values: dict[str, Any]) -> None:
    """Status samt passender Datumsfelder (wie services/invoices.py::apply_invoice_status)."""
    invoice.invoice_status = target
    if target == InvoiceStatus.ISSUED:
        invoice.invoice_date = (
            _as_date(values.get("invoice_date")) or invoice.invoice_date or date.today()
        )
        due = _as_date(values.get("payment_due_date"))
        if due is not None:
            invoice.payment_due_date = due
    if target == InvoiceStatus.PAID:
        invoice.paid_at = datetime.now(UTC)


def apply_staffing_invoice_issue(session: Session, approval: ApprovalRequest) -> None:
    """Wird beim Genehmigen einer Freigabe-Anfrage aufgerufen (services/approvals.py)."""
    invoice = session.get(StaffingInvoice, approval.entity_id)
    if invoice is None:
        raise EntityNotFoundError("Rechnung nicht gefunden")
    if invoice.invoice_status != InvoiceStatus.DRAFT:
        raise ConflictError("Die Rechnung ist nicht mehr im Entwurf.")
    apply_status(invoice, InvoiceStatus.ISSUED, approval.proposed_values or {})


class StaffingInvoiceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- Lesen --------------------------------------------------------------------------------

    def _get(self, invoice_id: uuid.UUID) -> StaffingInvoice:
        invoice = self.session.get(StaffingInvoice, invoice_id)
        if invoice is None:
            raise EntityNotFoundError("Rechnung nicht gefunden")
        return invoice

    def read(self, invoice: StaffingInvoice) -> StaffingInvoiceRead:
        client = self.session.get(ClientCompany, invoice.client_company_id)
        lines = self.session.scalars(
            select(StaffingInvoiceLine)
            .where(StaffingInvoiceLine.invoice_id == invoice.id)
            .order_by(StaffingInvoiceLine.worker_name, StaffingInvoiceLine.period_start)
        ).all()
        pending = ApprovalService(self.session).pending_for(ENTITY_TYPE, invoice.id)
        return StaffingInvoiceRead(
            id=invoice.id,
            created_at=invoice.created_at,
            updated_at=invoice.updated_at,
            client_company_id=invoice.client_company_id,
            client_name=client.name if client else "Unbekannt",
            period_start=invoice.period_start,
            period_end=invoice.period_end,
            amount_net=invoice.amount_net,
            vat_rate=invoice.vat_rate,
            amount_gross=invoice.amount_gross,
            invoice_status=invoice.invoice_status,
            invoice_date=invoice.invoice_date,
            payment_due_date=invoice.payment_due_date,
            paid_at=invoice.paid_at,
            created_by_user_id=invoice.created_by_user_id,
            notes=invoice.notes,
            approval_pending=bool(pending),
            lines=[StaffingInvoiceLineRead.model_validate(line) for line in lines],
        )

    def get_read(self, invoice_id: uuid.UUID) -> StaffingInvoiceRead:
        return self.read(self._get(invoice_id))

    def list_invoices(
        self, owner_scope: list[uuid.UUID] | None, *, offset: int = 0, limit: int = 200
    ) -> list[StaffingInvoiceRead]:
        statement = select(StaffingInvoice).order_by(StaffingInvoice.created_at.desc())
        if owner_scope is not None:
            statement = statement.where(StaffingInvoice.created_by_user_id.in_(owner_scope))
        invoices = self.session.scalars(statement.offset(offset).limit(limit)).all()
        return [self.read(invoice) for invoice in invoices]

    def billable_timesheets(
        self, owner_scope: list[uuid.UUID] | None
    ) -> list[StaffingBillableTimesheetRead]:
        """Freigegebene Stundenzettel ohne Rechnung, nur aus Einsätzen im eigenen Bereich."""
        billed = select(StaffingInvoiceLine.timesheet_id).where(
            StaffingInvoiceLine.timesheet_id.is_not(None)
        )
        hours = (
            select(func.coalesce(func.sum(StaffingTimesheetEntry.hours), 0))
            .where(StaffingTimesheetEntry.timesheet_id == StaffingTimesheet.id)
            .correlate(StaffingTimesheet)
            .scalar_subquery()
        )
        statement = (
            select(
                StaffingTimesheet,
                StaffingAssignment,
                Candidate.first_name,
                Candidate.last_name,
                ClientCompany.name,
                hours,
            )
            .join(StaffingAssignment, StaffingAssignment.id == StaffingTimesheet.assignment_id)
            .join(StaffingWorker, StaffingWorker.id == StaffingAssignment.worker_id)
            .join(Candidate, Candidate.id == StaffingWorker.candidate_id)
            .join(ClientCompany, ClientCompany.id == StaffingAssignment.client_company_id)
            .where(
                StaffingTimesheet.status == StaffingTimesheetStatus.APPROVED,
                StaffingTimesheet.id.not_in(billed),
            )
            .order_by(ClientCompany.name, StaffingTimesheet.period_start)
        )
        if owner_scope is not None:
            statement = statement.where(StaffingAssignment.owner_user_id.in_(owner_scope))
        result = []
        for sheet, assignment, first, last, client_name, total in self.session.execute(statement):
            result.append(
                StaffingBillableTimesheetRead(
                    timesheet_id=sheet.id,
                    assignment_id=assignment.id,
                    worker_name=_name(first, last),
                    client_company_id=assignment.client_company_id,
                    client_name=client_name,
                    period_start=sheet.period_start,
                    period_end=sheet.period_end,
                    total_hours=Decimal(total),
                    has_rate=assignment.billing_rate is not None,
                )
            )
        return result

    # --- Entwurf erstellen --------------------------------------------------------------------

    def create_draft(
        self,
        payload: StaffingInvoiceCreate,
        actor: User,
        owner_scope: list[uuid.UUID] | None,
    ) -> StaffingInvoiceRead:
        ids = list(dict.fromkeys(payload.timesheet_ids))
        rows = self.session.execute(
            select(StaffingTimesheet, StaffingAssignment)
            .join(StaffingAssignment, StaffingAssignment.id == StaffingTimesheet.assignment_id)
            .where(StaffingTimesheet.id.in_(ids))
        ).all()
        by_id = {sheet.id: (sheet, assignment) for sheet, assignment in rows}
        for timesheet_id in ids:
            found = by_id.get(timesheet_id)
            # Fremd UND nicht existent: dieselbe Meldung (kein Hinweis auf fremde Zettel).
            if found is None or (
                owner_scope is not None and found[1].owner_user_id not in owner_scope
            ):
                raise EntityNotFoundError("Stundenzettel nicht gefunden")
        sheets = [by_id[i] for i in ids]
        clients = {assignment.client_company_id for _, assignment in sheets}
        if len(clients) != 1:
            raise BusinessRuleError("Eine Rechnung kann nur Stundenzettel eines Kunden enthalten.")
        client_id = next(iter(clients))
        billed = self.session.scalars(
            select(StaffingInvoiceLine.timesheet_id).where(
                StaffingInvoiceLine.timesheet_id.in_(ids)
            )
        ).all()
        if billed:
            raise ConflictError("Mindestens ein Stundenzettel ist schon abgerechnet.")
        vat = get_settings().default_vat_rate
        lines: list[StaffingInvoiceLine] = []
        for sheet, assignment in sheets:
            if sheet.status != StaffingTimesheetStatus.APPROVED:
                raise BusinessRuleError(
                    f"Der Stundenzettel {sheet.period_start:%d.%m.%Y} bis "
                    f"{sheet.period_end:%d.%m.%Y} ist noch nicht vom Kunden freigegeben."
                )
            worker = self.session.get(StaffingWorker, assignment.worker_id)
            candidate = self.session.get(Candidate, worker.candidate_id) if worker else None
            worker_name = _name(
                candidate.first_name if candidate else None,
                candidate.last_name if candidate else None,
            )
            if assignment.billing_rate is None:
                raise BusinessRuleError(
                    f"Für den Einsatz von {worker_name} ist kein Verrechnungssatz hinterlegt "
                    "(nur Admins können ihn eintragen)."
                )
            total_hours = self.session.scalar(
                select(func.coalesce(func.sum(StaffingTimesheetEntry.hours), 0)).where(
                    StaffingTimesheetEntry.timesheet_id == sheet.id
                )
            )
            hours = Decimal(total_hours or 0)
            if hours <= 0:
                raise BusinessRuleError(
                    f"Der Stundenzettel von {worker_name} enthält keine Stunden."
                )
            lines.append(
                StaffingInvoiceLine(
                    timesheet_id=sheet.id,
                    assignment_id=assignment.id,
                    worker_name=worker_name,
                    description=(
                        f"Arbeitnehmerüberlassung {worker_name}, "
                        f"{sheet.period_start:%d.%m.%Y} bis {sheet.period_end:%d.%m.%Y}"
                    ),
                    period_start=sheet.period_start,
                    period_end=sheet.period_end,
                    hours=hours,
                    rate=assignment.billing_rate,
                    amount_net=_money(hours * assignment.billing_rate),
                )
            )
        net = sum((line.amount_net for line in lines), Decimal("0"))
        invoice = StaffingInvoice(
            client_company_id=client_id,
            period_start=min(line.period_start for line in lines),
            period_end=max(line.period_end for line in lines),
            amount_net=net,
            vat_rate=vat,
            amount_gross=_money(net * (Decimal("1") + vat / Decimal("100"))),
            created_by_user_id=actor.id,
            notes=payload.notes,
        )
        self.session.add(invoice)
        self.session.flush()
        for line in lines:
            line.invoice_id = invoice.id
            self.session.add(line)
        audit.log_created(
            self.session,
            ENTITY_INVOICE,
            invoice.id,
            {
                "client_company_id": client_id,
                "amount_net": net,
                "amount_gross": invoice.amount_gross,
                "timesheets": len(lines),
            },
            actor.email,
        )
        self.session.commit()
        return self.read(invoice)

    # --- Status -------------------------------------------------------------------------------

    def change_status(
        self, invoice_id: uuid.UUID, change: InvoiceStatusChange, actor: User
    ) -> tuple[StaffingInvoice, ApprovalRequest | None]:
        invoice = self._get(invoice_id)
        old = invoice.invoice_status
        target = change.invoice_status
        if target not in ALLOWED_INVOICE_TRANSITIONS[old]:
            raise BusinessRuleError(
                f"Rechnungsstatus {old.value} -> {target.value} ist nicht erlaubt"
            )
        values = change.model_dump(exclude={"invoice_status"}, exclude_none=True, mode="json")

        if needs_approval(actor):
            # Nicht-Admins: nur Entwurf stornieren oder das Stellen beantragen; alles Weitere
            # (faellig, bezahlt, Storno gestellter Rechnungen) bleibt dem Admin.
            if old != InvoiceStatus.DRAFT or target not in (
                InvoiceStatus.ISSUED,
                InvoiceStatus.CANCELLED,
            ):
                raise PermissionDeniedError("Diese Rechnungsänderung ist Admins vorbehalten.")
            if target == InvoiceStatus.ISSUED:
                client = self.session.get(ClientCompany, invoice.client_company_id)
                approval = ApprovalService(self.session).request(
                    entity_type=ENTITY_TYPE,
                    entity_id=invoice.id,
                    kind="invoice_issue",
                    requested_by=actor,
                    old_values={"invoice_status": old.value},
                    proposed_values={
                        "invoice_status": target.value,
                        "amount_net": str(invoice.amount_net),
                        "amount_gross": str(invoice.amount_gross),
                        "label": (
                            f"Überlassungsrechnung {client.name if client else ''} "
                            f"({invoice.amount_net} EUR netto)"
                        ).replace("  ", " "),
                        **values,
                    },
                )
                self.session.commit()
                return invoice, approval

        apply_status(invoice, target, values)
        if target == InvoiceStatus.CANCELLED:
            # Stundenzettel wieder abrechenbar machen; die Zeilen bleiben als Nachweis.
            for line in self.session.scalars(
                select(StaffingInvoiceLine).where(StaffingInvoiceLine.invoice_id == invoice.id)
            ):
                line.timesheet_id = None
        audit.log_event(
            self.session,
            ENTITY_INVOICE,
            invoice.id,
            "invoice_status_changed",
            actor.email,
            {"from": old.value, "to": target.value},
        )
        self.session.commit()
        return invoice, None

    # --- Export für die Lohnabrechnung -------------------------------------------------------

    def export_hours_csv(self, period_start: date, period_end: date) -> str:
        """Stunden je Leiharbeitnehmer und Kunde im Zeitraum (nur VOM KUNDEN FREIGEGEBENE Stunden),
        mit Stammdaten für Steuerberater oder Lohnsoftware. Format siehe docs/UEBERLASSUNG.md:
        Trennzeichen ';', Dezimalkomma, UTF-8 mit BOM, Zeilenende CRLF."""
        if period_end < period_start:
            raise BusinessRuleError("Das Ende liegt vor dem Beginn.")
        statement = (
            select(
                StaffingWorker,
                Candidate,
                ClientCompany.name,
                func.count(StaffingTimesheetEntry.id),
                func.sum(StaffingTimesheetEntry.hours),
                func.sum(StaffingTimesheetEntry.break_minutes),
            )
            .join(Candidate, Candidate.id == StaffingWorker.candidate_id)
            .join(StaffingAssignment, StaffingAssignment.worker_id == StaffingWorker.id)
            .join(ClientCompany, ClientCompany.id == StaffingAssignment.client_company_id)
            .join(StaffingTimesheet, StaffingTimesheet.assignment_id == StaffingAssignment.id)
            .join(
                StaffingTimesheetEntry, StaffingTimesheetEntry.timesheet_id == StaffingTimesheet.id
            )
            .where(
                StaffingTimesheet.status == StaffingTimesheetStatus.APPROVED,
                StaffingTimesheetEntry.work_date >= period_start,
                StaffingTimesheetEntry.work_date <= period_end,
            )
            .group_by(StaffingWorker.id, Candidate.id, ClientCompany.name)
            .order_by(Candidate.last_name, Candidate.first_name, ClientCompany.name)
        )
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        writer.writerow(CSV_HEADER)
        for worker, candidate, client_name, days, hours, breaks in self.session.execute(statement):
            writer.writerow(
                [
                    _cell(candidate.candidate_number),
                    _cell(candidate.last_name),
                    _cell(candidate.first_name),
                    _cell(client_name),
                    _cell(worker.pay_grade),
                    _num(worker.weekly_hours),
                    _num(worker.hourly_wage),
                    _date(worker.entry_date),
                    _date(worker.exit_date),
                    _date(period_start),
                    _date(period_end),
                    int(days or 0),
                    _num(hours),
                    int(breaks or 0),
                ]
            )
        return "﻿" + buffer.getvalue()


CSV_HEADER = [
    "Personalnummer",
    "Nachname",
    "Vorname",
    "Kunde",
    "Entgeltgruppe",
    "Wochenstunden",
    "Stundenlohn EUR",
    "Eintritt",
    "Austritt",
    "Zeitraum von",
    "Zeitraum bis",
    "Arbeitstage",
    "Stunden",
    "Pausen Minuten",
]


def _cell(value: str | None) -> str:
    """Text für eine Tabellenzelle. Beginnt er mit =, +, -, @ oder einem Steuerzeichen, hielte
    Excel ihn für eine Formel (CSV-Injection, die Namen kommen von Nutzern): ein Apostroph
    davor macht ihn zu Text."""
    text = (value or "").strip()
    if text and text[0] in "=+-@\t\r\n":
        return "'" + text
    return text


def _num(value: Decimal | float | int | None) -> str:
    if value is None:
        return ""
    return f"{Decimal(value):.2f}".replace(".", ",")


def _date(value: date | None) -> str:
    return "" if value is None else f"{value:%d.%m.%Y}"
