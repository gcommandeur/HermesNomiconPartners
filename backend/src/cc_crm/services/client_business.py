# NOMICON: "Geschaeft mit dieser Kanzlei" - nur in der Nomicon-Kopie.
"""Prozesse, Einsaetze, Fristen und Umsatz einer Kanzlei bzw. eines Kunden an einer Stelle. Es zeigt
nur, was der Nutzer ohnehin sehen darf: Ansicht Direct fuer Prozesse, Ansicht Ueberlassung fuer
Einsaetze und Fristen, Admin fuer Betraege; Prozesse und Einsaetze zusaetzlich im Owner-Scope."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cc_crm.api.dependencies import process_owner_scope, shared_submission_ids
from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import InvoiceStatus, SubmissionStatus
from cc_crm.models.recruiting import Fee, Placement
from cc_crm.models.staffing import StaffingAssignment, StaffingInvoice, StaffingWorker
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.user import User
from cc_crm.repositories.staffing import candidate_display_name
from cc_crm.schemas.client_business import (
    ClientAssignmentRead,
    ClientBusinessRead,
    ClientProcessRead,
    ClientRevenueRead,
)
from cc_crm.services.access_views import VIEW_DIRECT, VIEW_STAFFING, get_views
from cc_crm.services.staffing_overview import pair_deadlines


def _names(session: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return {
        u.id: u.display_name or u.email
        for u in session.scalars(select(User).where(User.id.in_(wanted))).all()
    }


def client_business(
    session: Session, user: User, client_id: uuid.UUID, today: date
) -> ClientBusinessRead:
    views = get_views(session, user)
    scope = process_owner_scope(user, session)  # Prozesse und Einsaetze: gleiche Regel
    processes = None
    if VIEW_DIRECT in views:
        statement = (
            select(CandidateSubmission, Candidate.first_name, Candidate.last_name)
            .join(Candidate, Candidate.id == CandidateSubmission.candidate_id)
            .where(
                CandidateSubmission.client_company_id == client_id,
                CandidateSubmission.status != SubmissionStatus.CANCELLED,
            )
            .order_by(CandidateSubmission.last_activity_at.desc())
        )
        rows = session.execute(statement).all()
        shared = set(shared_submission_ids(user, session))
        visible = [
            r for r in rows if scope is None or r[0].owner_user_id in scope or r[0].id in shared
        ]
        owners = _names(session, {r[0].owner_user_id for r in visible})
        processes = [
            ClientProcessRead(
                id=r[0].id,
                candidate_name=candidate_display_name(r[1], r[2]),
                status=r[0].status.value,
                owner_name=owners.get(r[0].owner_user_id) if r[0].owner_user_id else None,
                expected_fee=r[0].expected_fee,
            )
            for r in visible
        ]
    assignments = None
    deadlines = None
    if VIEW_STAFFING in views:
        assignment_statement = (
            select(StaffingAssignment, Candidate.first_name, Candidate.last_name)
            .join(StaffingWorker, StaffingWorker.id == StaffingAssignment.worker_id)
            .join(Candidate, Candidate.id == StaffingWorker.candidate_id)
            .where(StaffingAssignment.client_company_id == client_id)
            .order_by(StaffingAssignment.start_date.desc())
        )
        assignment_rows = [
            arow
            for arow in session.execute(assignment_statement).all()
            if scope is None or arow[0].owner_user_id in scope
        ]
        owners = _names(session, {arow[0].owner_user_id for arow in assignment_rows})
        assignments = [
            ClientAssignmentRead(
                id=arow[0].id,
                worker_name=candidate_display_name(arow[1], arow[2]),
                status=arow[0].status.value,
                start_date=arow[0].start_date,
                end_date=arow[0].actual_end_date or arow[0].planned_end_date,
                owner_name=owners.get(arow[0].owner_user_id) if arow[0].owner_user_id else None,
            )
            for arow in assignment_rows
        ]
        deadlines = [
            d for d in pair_deadlines(session, scope, today) if d.client_company_id == client_id
        ]
    revenue = None
    if user.is_admin:
        fees = session.scalar(
            select(func.coalesce(func.sum(Fee.amount_net), 0))
            .join(Placement, Placement.id == Fee.placement_id)
            .join(CandidateSubmission, CandidateSubmission.id == Placement.submission_id)
            .where(
                CandidateSubmission.client_company_id == client_id,
                Fee.invoice_status == InvoiceStatus.PAID,
            )
        )
        staffing = session.scalar(
            select(func.coalesce(func.sum(StaffingInvoice.amount_net), 0)).where(
                StaffingInvoice.client_company_id == client_id,
                StaffingInvoice.invoice_status.in_(
                    (InvoiceStatus.ISSUED, InvoiceStatus.DUE, InvoiceStatus.PAID)
                ),
            )
        )
        revenue = ClientRevenueRead(
            placement_fees_paid=Decimal(fees or 0), staffing_invoiced=Decimal(staffing or 0)
        )
    return ClientBusinessRead(
        processes=processes, assignments=assignments, deadlines=deadlines, revenue=revenue
    )
