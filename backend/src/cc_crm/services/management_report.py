# NOMICON: Ansicht "Gesamt" (Geschaeftsfuehrung) - nur in der Nomicon-Kopie.
"""Rohertrag, Prognose, Kunden mit beiden Geschaeften, Uebernahme-Quote und Alarme. Nur fuer Admins
(Route mit Ansicht "management"); enthaelt Marge und damit Lohnbezug - nie fuer andere sichtbar."""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cc_crm.models.candidate import Candidate  # noqa: F401  (Beziehungen laden)
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import InvoiceStatus, SubmissionStatus
from cc_crm.models.recruiting import Fee
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingInvoice,
    StaffingTimesheet,
    StaffingTimesheetEntry,
    StaffingTimesheetStatus,
    StaffingWorker,
)
from cc_crm.models.submission import CandidateSubmission
from cc_crm.schemas.management import (
    BothBusinessClientRead,
    ForecastRead,
    GrossProfitRead,
    ManagementAlertRead,
    ManagementOverviewRead,
    TakeoverRateRead,
)
from cc_crm.services.commission_settings import load_config as load_commission_config
from cc_crm.services.engagement_status import ACTIVE_PROCESS_STATUSES
from cc_crm.services.management_calc import (
    DirectItem,
    StaffingItem,
    direct_forecast,
    margin_per_hour,
    money,
    period_bounds,
    staffing_forecast,
    staffing_margin,
)
from cc_crm.services.staffing_deadline_job import pair_deadline
from cc_crm.services.staffing_overview import license_status, pair_deadlines
from cc_crm.services.staffing_settings import load_config as load_deadline_config

ASSUMPTIONS = [
    "Rohertrag Direct = bezahlte Vermittlungshonorare (netto) im Zeitraum.",
    "Rohertrag Überlassung = freigegebene Stunden × (Verrechnungssatz − Stundenlohn × "
    "Arbeitgeber-Faktor); der Faktor ist der einstellbare Arbeitgeber-Faktor des "
    "Provisionsmodells. Keine Lohn-, Steuer- oder Sozialversicherungsberechnung.",
    "Prognose Direct = erwartete Fee × Abschlusswahrscheinlichkeit laufender Prozesse; ohne Fee "
    "oder Wahrscheinlichkeit fehlt ein Prozess in der Summe und wird gezählt.",
    "Prognose Überlassung = Marge je Stunde × Wochenstunden × Restwochen aktiver Einsätze bis "
    "zum geplanten Ende, nie über die Höchstüberlassungsdauer hinaus.",
]


def _start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _end(day: date) -> datetime:
    return datetime.combine(day, time.max, tzinfo=UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _gross_profit(session: Session, start: date, end: date, factor: Decimal) -> GrossProfitRead:
    direct = Decimal(
        session.scalar(
            select(func.coalesce(func.sum(Fee.amount_net), 0)).where(
                Fee.invoice_status == InvoiceStatus.PAID,
                Fee.paid_at >= _start(start),
                Fee.paid_at <= _end(end),
            )
        )
        or 0
    )
    hours_by_sheet = dict(
        session.execute(
            select(
                StaffingTimesheetEntry.timesheet_id, func.sum(StaffingTimesheetEntry.hours)
            ).group_by(StaffingTimesheetEntry.timesheet_id)
        ).all()
    )
    margin_total = Decimal("0")
    hours_total = Decimal("0")
    missing = 0
    rows = session.execute(
        select(StaffingTimesheet, StaffingAssignment, StaffingWorker)
        .join(StaffingAssignment, StaffingAssignment.id == StaffingTimesheet.assignment_id)
        .join(StaffingWorker, StaffingWorker.id == StaffingAssignment.worker_id)
        .where(
            StaffingTimesheet.status == StaffingTimesheetStatus.APPROVED,
            StaffingTimesheet.decided_at >= _start(start),
            StaffingTimesheet.decided_at <= _end(end),
        )
    ).all()
    for sheet, assignment, worker in rows:
        rate = assignment.billing_rate
        wage = assignment.hourly_wage if assignment.hourly_wage is not None else worker.hourly_wage
        if rate is None or wage is None:
            missing += 1
            continue
        hours = Decimal(hours_by_sheet.get(sheet.id) or 0)
        hours_total += hours
        margin_total += staffing_margin(hours, Decimal(rate), Decimal(wage), factor)
    staffing = money(margin_total)
    return GrossProfitRead(
        direct=money(direct),
        staffing=staffing,
        total=money(direct + staffing),
        staffing_hours=hours_total,
        staffing_missing_rates=missing,
    )


def _forecast(session: Session, today: date, factor: Decimal) -> ForecastRead:
    processes = session.execute(
        select(CandidateSubmission.expected_fee, CandidateSubmission.closing_probability).where(
            CandidateSubmission.status.in_(ACTIVE_PROCESS_STATUSES),
            CandidateSubmission.archived_at.is_(None),
            CandidateSubmission.closed_at.is_(None),
        )
    ).all()
    direct = direct_forecast(
        DirectItem(
            Decimal(fee) if fee is not None else None,
            Decimal(str(probability)) if probability is not None else None,
        )
        for fee, probability in processes
    )
    config = load_deadline_config(session)
    items = []
    rows = session.execute(
        select(StaffingAssignment, StaffingWorker)
        .join(StaffingWorker, StaffingWorker.id == StaffingAssignment.worker_id)
        .where(StaffingAssignment.status == StaffingAssignmentStatus.ACTIVE)
    ).all()
    for assignment, worker in rows:
        rate = assignment.billing_rate
        wage = assignment.hourly_wage if assignment.hourly_wage is not None else worker.hourly_wage
        deadline = pair_deadline(
            session, assignment.worker_id, assignment.client_company_id, today, config
        )
        items.append(
            StaffingItem(
                margin_per_hour=(
                    margin_per_hour(Decimal(rate), Decimal(wage), factor)
                    if rate is not None and wage is not None
                    else None
                ),
                weekly_hours=Decimal(worker.weekly_hours)
                if worker.weekly_hours is not None
                else None,
                planned_end=assignment.planned_end_date,
                max_end=deadline.max_end_date,
            )
        )
    staffing = staffing_forecast(items, today)
    return ForecastRead(
        direct_weighted=direct.weighted,
        direct_without_probability=direct.without_probability,
        direct_without_fee=direct.without_fee,
        staffing_margin=staffing.margin,
        staffing_counted=staffing.counted,
        staffing_excluded=staffing.excluded,
        total=money(direct.weighted + staffing.margin),
    )


def _business_overlap(
    session: Session,
) -> tuple[list[BothBusinessClientRead], TakeoverRateRead]:
    processes: dict[uuid.UUID, int] = defaultdict(int)
    placed: dict[uuid.UUID, int] = defaultdict(int)
    placed_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for candidate_id, client_id, status in session.execute(
        select(
            CandidateSubmission.candidate_id,
            CandidateSubmission.client_company_id,
            CandidateSubmission.status,
        ).where(
            CandidateSubmission.client_company_id.is_not(None),
            CandidateSubmission.status != SubmissionStatus.CANCELLED,
        )
    ):
        if client_id is None:
            continue
        processes[client_id] += 1
        if status == SubmissionStatus.PLACEMENT:
            placed[client_id] += 1
            placed_pairs.add((candidate_id, client_id))
    assignments: dict[uuid.UUID, int] = defaultdict(int)
    pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for candidate_id, client_id in session.execute(
        select(StaffingWorker.candidate_id, StaffingAssignment.client_company_id)
        .join(StaffingAssignment, StaffingAssignment.worker_id == StaffingWorker.id)
        .where(StaffingAssignment.status != StaffingAssignmentStatus.ABORTED)
    ):
        assignments[client_id] += 1
        pairs.add((candidate_id, client_id))
    taken_by_client: dict[uuid.UUID, int] = defaultdict(int)
    for _candidate_id, client_id in pairs & placed_pairs:
        taken_by_client[client_id] += 1
    both = sorted(set(processes) & set(assignments))
    names = (
        {
            row.id: row.name
            for row in session.execute(
                select(ClientCompany.id, ClientCompany.name).where(ClientCompany.id.in_(both))
            )
        }
        if both
        else {}
    )
    clients = [
        BothBusinessClientRead(
            client_id=client_id,
            client_name=names.get(client_id, "Kanzlei"),
            processes=processes[client_id],
            assignments=assignments[client_id],
            placements=placed[client_id],
            taken_over=taken_by_client[client_id],
        )
        for client_id in both
    ]
    clients.sort(key=lambda c: (-(c.processes + c.assignments), c.client_name))
    taken = len(pairs & placed_pairs)
    takeover = TakeoverRateRead(
        pairs=len(pairs),
        taken_over=taken,
        rate=(Decimal(taken) / Decimal(len(pairs))).quantize(Decimal("0.0001")) if pairs else None,
    )
    return clients, takeover


def _alerts(session: Session, today: date) -> list[ManagementAlertRead]:
    alerts: list[ManagementAlertRead] = []
    deadlines = pair_deadlines(session, None, today)
    red = sum(d.traffic == "red" for d in deadlines)
    yellow = sum(d.traffic == "yellow" for d in deadlines)
    if red:
        alerts.append(
            ManagementAlertRead(
                kind="deadline_red",
                severity="red",
                count=red,
                text=f"{red} Überlassungsfristen dringend oder überschritten",
                href="/ueberlassung",
            )
        )
    if yellow:
        alerts.append(
            ManagementAlertRead(
                kind="deadline_yellow",
                severity="yellow",
                count=yellow,
                text=f"{yellow} Überlassungsfristen laufen bald ab",
                href="/ueberlassung",
            )
        )
    license_ = license_status(session, today)
    if not license_.valid or license_.traffic != "green":
        alerts.append(
            ManagementAlertRead(
                kind="license",
                severity="red" if not license_.valid or license_.traffic == "red" else "yellow",
                count=1,
                text=(
                    "Keine gültige AÜG-Erlaubnis hinterlegt"
                    if not license_.valid
                    else f"AÜG-Erlaubnis läuft in {license_.days_remaining} Tagen ab"
                ),
                href="/ueberlassung/compliance",
            )
        )
    overdue_fees = (
        session.scalar(
            select(func.count())
            .select_from(Fee)
            .where(
                Fee.invoice_status.in_((InvoiceStatus.ISSUED, InvoiceStatus.DUE)),
                Fee.payment_due_date < today,
            )
        )
        or 0
    )
    overdue_staffing = (
        session.scalar(
            select(func.count())
            .select_from(StaffingInvoice)
            .where(
                StaffingInvoice.invoice_status.in_((InvoiceStatus.ISSUED, InvoiceStatus.DUE)),
                StaffingInvoice.payment_due_date < today,
            )
        )
        or 0
    )
    if overdue_fees + overdue_staffing:
        alerts.append(
            ManagementAlertRead(
                kind="invoices_overdue",
                severity="red",
                count=overdue_fees + overdue_staffing,
                text=f"{overdue_fees + overdue_staffing} Rechnungen überfällig",
                href="/freigaben",
            )
        )
    unowned = (
        session.scalar(
            select(func.count())
            .select_from(CandidateSubmission)
            .where(CandidateSubmission.owner_user_id.is_(None))
        )
        or 0
    )
    if unowned:
        alerts.append(
            ManagementAlertRead(
                kind="processes_without_owner",
                severity="yellow",
                count=unowned,
                text=f"{unowned} Prozesse ohne Verantwortlichen",
                href="/prozesse/ohne-verantwortlichen",
            )
        )
    return alerts


def overview(session: Session, period: str, today: date) -> ManagementOverviewRead:
    start, end = period_bounds(period, today)
    factor = load_commission_config(session).general.employer_factor
    clients, takeover = _business_overlap(session)
    return ManagementOverviewRead.model_validate(
        {
            "period": period,
            "date_from": start,
            "date_to": end,
            "employer_factor": factor,
            "gross_profit": _gross_profit(session, start, end, factor),
            "forecast": _forecast(session, today, factor),
            "both_business_clients": clients,
            "takeover": takeover,
            "alerts": _alerts(session, today),
            "assumptions": ASSUMPTIONS,
        }
    )
