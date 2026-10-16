# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Deals (Vermittlungsbonus) und Ueberlassungs-Aufschluesselung je Quartal.

Was ein Deal ist (Karriereplan Oktober 2026, vom Nutzer bestaetigt):
- Vermittlung: ein Prozess mit Platzierung (`Placement`). Verantwortlich: Owner des Prozesses.
  Zeitpunkt: Zahlungsdatum der ersten bezahlten Fee des Placements.
- Ueberlassung: ein Einsatz (`StaffingAssignment`), egal wie viele Monate er laeuft (6 Monate =
  EIN Deal). Verantwortlich: Disponent des Einsatzes (ersatzweise Ersteller der Rechnung).
  Zeitpunkt: Zahlungsdatum der ersten bezahlten Rechnung des Einsatzes.
- VERLAENGERUNG = NEUER DEAL. Erkannt wird sie technisch so:
  * Wird das geplante Ende eines Einsatzes nach hinten verschoben, schreibt
    `StaffingAssignmentService.update` eine Zeile in `staffing_assignment_extensions`
    (`previous_end` = altes Ende). Der Einsatz zerfaellt damit in Abschnitte: Abschnitt 0 bis zum
    ersten `previous_end`, Abschnitt k nach dem k-ten. Eine Rechnungszeile gehoert zum Abschnitt
    "Anzahl der Verlaengerungen mit previous_end < Ende des abgerechneten Zeitraums".
    Jeder Abschnitt mit mindestens einer bezahlten Rechnung ist EIN Deal; sein Zeitpunkt ist das
    erste Zahlungsdatum im Abschnitt.
  * Ein Folgeeinsatz (neuer Einsatz, auch beim selben Kunden oder bei einem anderen Kunden) ist ein
    neuer `StaffingAssignment` und damit von selbst ein neuer Deal.
- Ohne Zahlung kein Deal: Entwuerfe, gestellte und faellige Rechnungen zaehlen nicht.
- Ein spaeter abgebrochener Einsatz (Annahme): bereits entstandene Deals bleiben, nicht bezahlte
  Rechnungen zaehlen nicht (Deals haengen nur an Zahlungen, nicht am Einsatzstatus)."""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cc_crm.models.enums import InvoiceStatus
from cc_crm.models.recruiting import Fee, Placement
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentExtension,
    StaffingInvoice,
    StaffingInvoiceLine,
)
from cc_crm.models.submission import CandidateSubmission


def _as_date(value: datetime) -> date:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC).date()


@dataclass(frozen=True)
class DealCount:
    placement: int = 0
    staffing: int = 0


def segment_of(previous_ends: list[date], period_end: date) -> int:
    """Abschnitt einer abgerechneten Zeile: Anzahl der Verlaengerungen vor ihrem Zeitraum."""
    return sum(1 for previous_end in previous_ends if previous_end < period_end)


def _extension_ends(session: Session) -> dict[uuid.UUID, list[date]]:
    ends: dict[uuid.UUID, list[date]] = defaultdict(list)
    for assignment_id, previous_end in session.execute(
        select(
            StaffingAssignmentExtension.assignment_id, StaffingAssignmentExtension.previous_end
        )
    ):
        ends[assignment_id].append(previous_end)
    return ends


def deals_for_quarter(
    session: Session, start: date, end: date, *, include_staffing: bool = True
) -> dict[uuid.UUID, DealCount]:
    """Deals je Mitarbeiter, deren Zahldatum im Quartal [start, end] liegt."""
    placement: dict[uuid.UUID, int] = defaultdict(int)
    staffing: dict[uuid.UUID, int] = defaultdict(int)

    fee_rows = session.execute(
        select(CandidateSubmission.owner_user_id, func.min(Fee.paid_at))
        .join(Placement, Placement.id == Fee.placement_id)
        .join(CandidateSubmission, CandidateSubmission.id == Placement.submission_id)
        .where(Fee.invoice_status == InvoiceStatus.PAID, Fee.paid_at.is_not(None))
        .group_by(Placement.id, CandidateSubmission.owner_user_id)
    )
    for owner, first_paid in fee_rows:
        if owner is not None and first_paid is not None and start <= _as_date(first_paid) <= end:
            placement[owner] += 1

    if include_staffing:
        extension_ends = _extension_ends(session)
        earliest: dict[tuple[uuid.UUID, int], tuple[datetime, uuid.UUID | None]] = {}
        line_rows = session.execute(
            select(
                StaffingInvoiceLine.assignment_id,
                StaffingInvoiceLine.period_end,
                StaffingInvoice.paid_at,
                StaffingAssignment.owner_user_id,
                StaffingInvoice.created_by_user_id,
            )
            .join(StaffingInvoice, StaffingInvoice.id == StaffingInvoiceLine.invoice_id)
            .join(StaffingAssignment, StaffingAssignment.id == StaffingInvoiceLine.assignment_id)
            .where(
                StaffingInvoice.invoice_status == InvoiceStatus.PAID,
                StaffingInvoice.paid_at.is_not(None),
            )
        )
        for assignment_id, period_end, paid_at, owner, creator in line_rows:
            if assignment_id is None or paid_at is None:
                continue
            segment = segment_of(extension_ends.get(assignment_id, []), period_end)
            key = (assignment_id, segment)
            known = earliest.get(key)
            if known is None or _as_date(paid_at) < _as_date(known[0]):
                earliest[key] = (paid_at, owner or creator)
        for paid_at, responsible in earliest.values():
            if responsible is not None and start <= _as_date(paid_at) <= end:
                staffing[responsible] += 1

    return {
        user: DealCount(placement.get(user, 0), staffing.get(user, 0))
        for user in set(placement) | set(staffing)
    }


@dataclass(frozen=True)
class StaffingAssignmentLine:
    """Aufschluesselung eines Einsatzes fuer ein Quartal (nur bezahlte Rechnungen)."""

    assignment_id: uuid.UUID
    worker_name: str
    paid_months: int
    revenue: Decimal


def staffing_breakdown(
    session: Session, user_id: uuid.UUID, start: date, end: date
) -> list[StaffingAssignmentLine]:
    """Je Einsatz des Disponenten: bezahlte Monate und Umsatz im Quartal nach Zahldatum.
    "Bezahlte Monate" sind die verschiedenen Kalendermonate der abgerechneten Zeitraeume."""
    rows = session.execute(
        select(
            StaffingInvoiceLine.assignment_id,
            StaffingInvoiceLine.worker_name,
            StaffingInvoiceLine.period_end,
            StaffingInvoiceLine.amount_net,
            StaffingInvoice.paid_at,
        )
        .join(StaffingInvoice, StaffingInvoice.id == StaffingInvoiceLine.invoice_id)
        .join(StaffingAssignment, StaffingAssignment.id == StaffingInvoiceLine.assignment_id)
        .where(
            StaffingInvoice.invoice_status == InvoiceStatus.PAID,
            StaffingInvoice.paid_at.is_not(None),
            func.coalesce(StaffingAssignment.owner_user_id, StaffingInvoice.created_by_user_id)
            == user_id,
        )
    )
    months: dict[uuid.UUID, set[tuple[int, int]]] = defaultdict(set)
    revenue: dict[uuid.UUID, Decimal] = defaultdict(lambda: Decimal("0"))
    names: dict[uuid.UUID, str] = {}
    for assignment_id, worker_name, period_end, amount, paid_at in rows:
        if assignment_id is None or paid_at is None:
            continue
        if not start <= _as_date(paid_at) <= end:
            continue
        months[assignment_id].add((period_end.year, period_end.month))
        revenue[assignment_id] += Decimal(amount)
        names[assignment_id] = worker_name
    return sorted(
        (
            StaffingAssignmentLine(
                a, names[a], len(months[a]), revenue[a].quantize(Decimal("0.01"))
            )
            for a in revenue
        ),
        key=lambda item: item.worker_name,
    )


def expected_revenue(session: Session, user_id: uuid.UUID, end: date) -> Decimal:
    """Hinweis "erwartet": gestellte oder faellige, noch NICHT bezahlte Rechnungen bis Quartalsende
    (Vermittlung und Ueberlassung). Fliesst nie in die Provision."""
    open_status = (InvoiceStatus.ISSUED, InvoiceStatus.DUE)
    fees = session.scalar(
        select(func.coalesce(func.sum(Fee.amount_net), 0))
        .join(Placement, Placement.id == Fee.placement_id)
        .join(CandidateSubmission, CandidateSubmission.id == Placement.submission_id)
        .where(
            Fee.invoice_status.in_(open_status),
            Fee.invoice_date <= end,
            CandidateSubmission.owner_user_id == user_id,
        )
    )
    lines = session.scalar(
        select(func.coalesce(func.sum(StaffingInvoiceLine.amount_net), 0))
        .join(StaffingInvoice, StaffingInvoice.id == StaffingInvoiceLine.invoice_id)
        .outerjoin(StaffingAssignment, StaffingAssignment.id == StaffingInvoiceLine.assignment_id)
        .where(
            StaffingInvoice.invoice_status.in_(open_status),
            StaffingInvoice.invoice_date <= end,
            func.coalesce(StaffingAssignment.owner_user_id, StaffingInvoice.created_by_user_id)
            == user_id,
        )
    )
    return (Decimal(fees or 0) + Decimal(lines or 0)).quantize(Decimal("0.01"))
