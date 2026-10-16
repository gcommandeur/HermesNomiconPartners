# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Umsatz je Mitarbeiter und Quartal aus Vermittlungshonoraren und Ueberlassungsrechnungen.

Welcher Umsatz zaehlt, ist EINSTELLBAR (`RevenueBasis`). Startwert laut Karriereplan: fuer
Vermittlung UND Ueberlassung nur bezahlte (Zahldatum). Dazu die Deals fuer den Bonus
(`commission_deals`, immer nach Zahldatum):
- Vermittlung: `Fee.amount_net`; Mitarbeiter = Verantwortlicher des Prozesses
  (`CandidateSubmission.owner_user_id`); Datum = Zahlungsdatum ("paid") bzw. Rechnungsdatum
  ("issued": gestellt, faellig oder bezahlt).
- Ueberlassung: `StaffingInvoiceLine.amount_net`; Mitarbeiter = Disponent des Einsatzes (ersatzweise
  Ersteller der Rechnung); Datum = Rechnungs- bzw. Zahlungsdatum je nach Einstellung.
Entwuerfe und stornierte Rechnungen zaehlen nie."""

import uuid
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.enums import InvoiceStatus
from cc_crm.models.recruiting import Fee, Placement
from cc_crm.models.staffing import StaffingAssignment, StaffingInvoice, StaffingInvoiceLine
from cc_crm.models.submission import CandidateSubmission
from cc_crm.services.commission_deals import deals_for_quarter
from cc_crm.services.commission_model import RevenueBasis

_ISSUED_OR_LATER = (InvoiceStatus.ISSUED, InvoiceStatus.DUE, InvoiceStatus.PAID)


@dataclass
class UserRevenue:
    fees: Decimal = Decimal("0")
    staffing: Decimal = Decimal("0")
    placement_deals: int = 0  # Deals mit Zahldatum im Quartal (Vermittlungsbonus)
    staffing_deals: int = 0

    @property
    def total(self) -> Decimal:
        return self.fees + self.staffing


@dataclass
class QuarterRevenue:
    by_user: dict[uuid.UUID, UserRevenue] = field(default_factory=dict)

    def add(
        self,
        user_id: uuid.UUID | None,
        *,
        fees: Decimal = Decimal("0"),
        staffing: Decimal = Decimal("0"),
    ) -> None:
        if user_id is None:
            return  # ohne Verantwortlichen keinem Mitarbeiter zuzuordnen
        entry = self.by_user.setdefault(user_id, UserRevenue())
        entry.fees += fees
        entry.staffing += staffing


def quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    if quarter not in (1, 2, 3, 4):
        raise ValueError("quarter muss 1 bis 4 sein")
    first_month = 3 * quarter - 2
    last_month = first_month + 2
    return date(year, first_month, 1), date(year, last_month, monthrange(year, last_month)[1])


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _day_end(day: date) -> datetime:
    return datetime.combine(day, time.max, tzinfo=UTC)


def quarter_revenue(
    session: Session, year: int, quarter: int, basis: RevenueBasis
) -> QuarterRevenue:
    start, end = quarter_bounds(year, quarter)
    result = QuarterRevenue()

    fee_statement = (
        select(Fee.amount_net, CandidateSubmission.owner_user_id)
        .join(Placement, Placement.id == Fee.placement_id)
        .join(CandidateSubmission, CandidateSubmission.id == Placement.submission_id)
    )
    if basis.placement_fees == "paid":
        fee_statement = fee_statement.where(
            Fee.invoice_status == InvoiceStatus.PAID,
            Fee.paid_at >= _day_start(start),
            Fee.paid_at <= _day_end(end),
        )
    else:
        fee_statement = fee_statement.where(
            Fee.invoice_status.in_(_ISSUED_OR_LATER),
            Fee.invoice_date >= start,
            Fee.invoice_date <= end,
        )
    for amount, owner in session.execute(fee_statement):
        result.add(owner, fees=Decimal(amount))

    if basis.include_staffing:
        line_statement = (
            select(
                StaffingInvoiceLine.amount_net,
                StaffingAssignment.owner_user_id,
                StaffingInvoice.created_by_user_id,
            )
            .join(StaffingInvoice, StaffingInvoice.id == StaffingInvoiceLine.invoice_id)
            .outerjoin(
                StaffingAssignment, StaffingAssignment.id == StaffingInvoiceLine.assignment_id
            )
        )
        if basis.staffing == "paid":
            line_statement = line_statement.where(
                StaffingInvoice.invoice_status == InvoiceStatus.PAID,
                StaffingInvoice.paid_at >= _day_start(start),
                StaffingInvoice.paid_at <= _day_end(end),
            )
        else:
            line_statement = line_statement.where(
                StaffingInvoice.invoice_status.in_(_ISSUED_OR_LATER),
                StaffingInvoice.invoice_date >= start,
                StaffingInvoice.invoice_date <= end,
            )
        for amount, assignment_owner, creator in session.execute(line_statement):
            result.add(assignment_owner or creator, staffing=Decimal(amount))

    deals = deals_for_quarter(session, start, end, include_staffing=basis.include_staffing)
    for user_id, count in deals.items():
        entry = result.by_user.setdefault(user_id, UserRevenue())
        entry.placement_deals = count.placement
        entry.staffing_deals = count.staffing
    return result
