# NOMICON: Demo-Daten für "Meine Provision" - nur erfundene Werte, nur lokal.
"""Rang für die Demo-Konten und neun Monate bezahlte Umsätze und Deals für den Demo-Vermittler.

Ziel: In der Demo zeigt "Meine Provision" für den Demo-Vermittler (Senior Consultant) in jedem der
letzten Monate einen Wert, und der Umsatz des LAUFENDEN Quartals liegt bei rund 70 % der
Beförderungsschwelle (Manager ab 96.000 € Quartalsumsatz). Je Monat entsteht eine bezahlte
Vermittlungs-Fee (Prozess mit Platzierung) und eine bezahlte Überlassungsrechnung (Einsatz, den der
Vermittler betreut); die Zahldaten liegen im jeweiligen Monat, der Umsatz zählt also nach Zahldatum.
Die Zeilen werden direkt als Datensätze angelegt (wie `seed_demo.py` es für Prozesse tut) - die
Beträge sind erfunden und gehören nur in eine lokale Dummy-Datenbank.

Idempotent: Jede Zeile trägt eine Kennung (Demo-Kandidat `demo.prov-…@example.com`); was es schon
gibt, wird nicht doppelt angelegt. Ränge werden nur gesetzt, wenn die Person noch keinen hat."""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.commission import CommissionUserRank  # noqa: E402
from cc_crm.models.engagement import CandidateEngagementPrefs  # noqa: E402
from cc_crm.models.enums import InvoiceStatus, SubmissionStatus  # noqa: E402
from cc_crm.models.recruiting import Fee, Placement  # noqa: E402
from cc_crm.models.staffing import (  # noqa: E402
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingInvoice,
    StaffingInvoiceLine,
    StaffingWorker,
    StaffingWorkerStatus,
)
from cc_crm.models.submission import CandidateSubmission  # noqa: E402
from cc_crm.models.user import User  # noqa: E402
from cc_crm.services.commission_revenue import month_bounds  # noqa: E402

MONTHS = 9  # Monate zurück (0 = laufender Monat)
# Rohwerte je Monat (Umsatz gesamt, EUR), Index = Monate zurück. Verschiedene Größen, damit die
# Quartale unterschiedliche Stufen erreichen.
RAW = {8: 31000, 7: 43000, 6: 58000, 5: 36000, 4: 49000, 3: 62000, 2: 41000, 1: 54000, 0: 40000}
HURDLE = Decimal("96000")  # Beförderung Senior Consultant -> Manager (Startwert des Modells)
TARGET_SHARE = Decimal("0.70")  # laufendes Quartal bei ca. 70 % der Schwelle
FEE_SHARE = Decimal("0.60")  # Rest: Überlassung
STAFFING_WORKERS = ("Mia Demo-Prov", "Jonas Demo-Prov", "Lena Demo-Prov")
VAT = Decimal("19")


def month_back(today: date, back: int) -> tuple[int, int]:
    index = today.year * 12 + today.month - 1 - back
    return index // 12, index % 12 + 1


def amounts(today: date) -> dict[int, Decimal]:
    """Umsatz je Monat zurück; die Monate des laufenden Quartals werden so skaliert, dass ihre Summe
    bei TARGET_SHARE der Beförderungsschwelle liegt."""
    result = {back: Decimal(value) for back, value in RAW.items()}
    in_quarter = list(range((today.month - 1) % 3 + 1))
    raw_total = sum(result[back] for back in in_quarter)
    target = (HURDLE * TARGET_SHARE).quantize(Decimal("1"))
    for back in in_quarter:
        result[back] = (result[back] * target / raw_total).quantize(Decimal("1"))
    return result


def paid_at(today: date, year: int, month: int) -> datetime:
    """Zahldatum im Monat (Mitte des Monats, im laufenden Monat höchstens heute)."""
    day = 15
    if (year, month) == (today.year, today.month):
        day = max(1, min(day, today.day))
    return datetime(year, month, day, 10, 0, tzinfo=UTC)


def _candidate(session: Session, key: str, first: str, last: str) -> Candidate | None:
    email = f"demo.prov-{key}@example.com"
    if session.scalar(select(Candidate.id).where(Candidate.email == email)) is not None:
        return None
    row = Candidate(first_name=first, last_name=last, email=email, city="Köln")
    session.add(row)
    session.flush()
    return row


def _set_rank(session: Session, user: User, rank_key: str, today: date) -> None:
    if session.scalar(select(CommissionUserRank.id).where(CommissionUserRank.user_id == user.id)):
        return
    session.add(
        CommissionUserRank(
            user_id=user.id,
            rank_key=rank_key,
            effective_from=date(today.year - 1, 1, 1),
            updated_by="seed-demo",
        )
    )


def _fee(
    session: Session, owner: User, client: ClientCompany, back: int, amount: Decimal, today: date
) -> bool:
    year, month = month_back(today, back)
    candidate = _candidate(session, f"fee{back}", f"Vermittelt{back}", "Demo-Prov")
    if candidate is None:
        return False
    paid = paid_at(today, year, month)
    submission = CandidateSubmission(
        candidate_id=candidate.id,
        client_company_id=client.id,
        status=SubmissionStatus.PLACEMENT,
        owner_user_id=owner.id,
        owner=owner.display_name,
        expected_fee=amount,
        fee_percentage=Decimal("25"),
        closing_probability=1.0,
        last_activity_at=paid,
        next_step="Abgeschlossen",
    )
    session.add(submission)
    session.flush()
    placement = Placement(
        submission_id=submission.id,
        start_date=paid.date(),
        final_salary=(amount * 4).quantize(Decimal("1")),
        fee_percentage=Decimal("25"),
        calculated_fee=amount,
        guarantee_period_months=6,
    )
    session.add(placement)
    session.flush()
    session.add(
        Fee(
            placement_id=placement.id,
            amount_net=amount,
            vat_rate=VAT,
            amount_gross=(amount * (1 + VAT / 100)).quantize(Decimal("0.01")),
            invoice_status=InvoiceStatus.PAID,
            invoice_date=paid.date(),
            payment_due_date=paid.date(),
            paid_at=paid,
        )
    )
    return True


def _worker_assignments(
    session: Session, owner: User, client: ClientCompany, today: date
) -> list[StaffingAssignment]:
    """Drei laufende Einsätze des Vermittlers (je einer ein Deal beim ersten bezahlten Monat)."""
    found: list[StaffingAssignment] = []
    for index, name in enumerate(STAFFING_WORKERS):
        first, last = name.split(" ", 1)
        candidate = _candidate(session, f"w{index}", first, last)
        if candidate is None:
            worker_row = session.scalar(
                select(StaffingWorker)
                .join(Candidate, Candidate.id == StaffingWorker.candidate_id)
                .where(Candidate.email == f"demo.prov-w{index}@example.com")
            )
            if worker_row is not None:
                assignment = session.scalar(
                    select(StaffingAssignment).where(StaffingAssignment.worker_id == worker_row.id)
                )
                if assignment is not None:
                    found.append(assignment)
            continue
        session.add(CandidateEngagementPrefs(candidate_id=candidate.id, open_for_staffing="yes"))
        worker = StaffingWorker(
            candidate_id=candidate.id,
            status=StaffingWorkerStatus.ACTIVE,
            entry_date=date(today.year - 1, 1, 1),
            hourly_wage=Decimal("15.40"),
            weekly_hours=Decimal("40"),
        )
        session.add(worker)
        session.flush()
        assignment = StaffingAssignment(
            worker_id=worker.id,
            client_company_id=client.id,
            owner_user_id=owner.id,
            start_date=date(today.year - 1, 12, 1),
            planned_end_date=date(today.year + 1, 6, 30),
            billing_rate=Decimal("27.80"),
            hourly_wage=Decimal("15.40"),
            status=StaffingAssignmentStatus.ACTIVE,
            activity="Kommissionierung",
        )
        session.add(assignment)
        session.flush()
        found.append(assignment)
    return found


def _staffing_invoice(
    session: Session,
    owner: User,
    assignment: StaffingAssignment,
    worker_name: str,
    back: int,
    amount: Decimal,
    today: date,
) -> bool:
    year, month = month_back(today, back)
    start, end = month_bounds(year, month)
    marker = f"Demo-Provision {year}-{month:02d} {assignment.id}"
    if session.scalar(select(StaffingInvoice.id).where(StaffingInvoice.notes == marker)):
        return False
    paid = paid_at(today, year, month)
    invoice = StaffingInvoice(
        client_company_id=assignment.client_company_id,
        period_start=start,
        period_end=end,
        amount_net=amount,
        vat_rate=VAT,
        amount_gross=(amount * (1 + VAT / 100)).quantize(Decimal("0.01")),
        invoice_status=InvoiceStatus.PAID,
        invoice_date=paid.date(),
        payment_due_date=paid.date(),
        paid_at=paid,
        created_by_user_id=owner.id,
        notes=marker,
    )
    session.add(invoice)
    session.flush()
    hours = Decimal("160")
    session.add(
        StaffingInvoiceLine(
            invoice_id=invoice.id,
            timesheet_id=None,
            assignment_id=assignment.id,
            worker_name=worker_name,
            description=f"Überlassung {month:02d}/{year}",
            period_start=start,
            period_end=end,
            hours=hours,
            rate=(amount / hours).quantize(Decimal("0.01")),
            amount_net=amount,
        )
    )
    return True


def seed_commission_demo(
    session: Session, admin: User, broker: User, colleague: User, today: date | None = None
) -> int:
    """Gibt die Zahl neu angelegter Monatszeilen (Fee oder Rechnung) zurück."""
    day = today or date.today()
    _set_rank(session, broker, "senior", day)
    _set_rank(session, admin, "manager", day)
    _set_rank(session, colleague, "consultant", day)
    client = session.scalar(select(ClientCompany).order_by(ClientCompany.name).limit(1))
    if client is None:
        return 0
    assignments = _worker_assignments(session, broker, client, day)
    created = 0
    for back, total in sorted(amounts(day).items(), reverse=True):
        fee_part = (total * FEE_SHARE).quantize(Decimal("1"))
        if _fee(session, broker, client, back, fee_part, day):
            created += 1
        if assignments:
            index = (MONTHS - 1 - back) % len(assignments)
            name = STAFFING_WORKERS[index]
            if _staffing_invoice(
                session, broker, assignments[index], name, back, total - fee_part, day
            ):
                created += 1
    session.flush()
    return created
