# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Arbeitnehmerüberlassung: Leiharbeitnehmer, Verträge, Einsätze, Erlaubnis, Fristen.

Rechte: Einsätze sind über den Disponenten gescopt (api/staffing_dependencies.py), jede Route
mit `assignment_id` im Pfad hat `AssignmentAccess`. Lohn und Verrechnungssatz sehen und setzen nur
Admins (services/staffing_visibility.py); Erlaubnis und Einstellungen ändern nur Admins."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy.orm import Session

from cc_crm.api.dependencies import AdminUser, CurrentUser, DatabaseSession
from cc_crm.api.staffing_dependencies import (
    AssignmentAccess,
    InvoiceAccess,
    TimesheetAccess,
    staffing_owner_scope,
)
from cc_crm.core.errors import EntityNotFoundError, PermissionDeniedError
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.staffing import StaffingAssignmentStatus, StaffingWorker, StaffingWorkerStatus
from cc_crm.repositories.staffing import StaffingWorkerRepository
from cc_crm.schemas.approval import ApprovalRequestRead, InvoiceStatusChange
from cc_crm.schemas.staffing import (
    StaffingAssignmentCreate,
    StaffingAssignmentDetail,
    StaffingAssignmentRead,
    StaffingAssignmentStatusChange,
    StaffingAssignmentUpdate,
    StaffingBillableTimesheetRead,
    StaffingChecklistItemUpdate,
    StaffingContractCreate,
    StaffingContractRead,
    StaffingContractUpdate,
    StaffingInvoiceCreate,
    StaffingInvoiceRead,
    StaffingInvoiceStatusResult,
    StaffingLicenseCreate,
    StaffingLicenseRead,
    StaffingLicenseUpdate,
    StaffingOfferInput,
    StaffingOfferResult,
    StaffingOverviewRead,
    StaffingPairDeadlineRead,
    StaffingPriorPeriodCreate,
    StaffingPriorPeriodRead,
    StaffingPriorPeriodUpdate,
    StaffingSettingsRead,
    StaffingSettingsUpdate,
    StaffingTakeoverInput,
    StaffingTakeoverPreview,
    StaffingTakeoverResult,
    StaffingTimesheetCreate,
    StaffingTimesheetEntriesUpdate,
    StaffingTimesheetRead,
    StaffingTimesheetSubmitResult,
    StaffingWorkerCreate,
    StaffingWorkerRead,
    StaffingWorkerUpdate,
    TakeoverFeeTierRead,
    TakeoverFeeTiersRead,
    TakeoverFeeTiersUpdate,
)
from cc_crm.schemas.staffing_candidates import (
    StaffingCandidateSummaryRead,
    StaffingCandidateSummaryRequest,
    StaffingWorkerTimesheetSummary,
)
from cc_crm.schemas.staffing_disposition import StaffingDispositionRead
from cc_crm.schemas.staffing_tasks import StaffingTasksRead
from cc_crm.services.approvals import ApprovalService
from cc_crm.services.engagement_status import ensure_no_conflict
from cc_crm.services.staffing_activation import StaffingActivationService
from cc_crm.services.staffing_assignments import (
    StaffingAssignmentService,
    StaffingContractService,
    assignment_read,
    contract_read,
)
from cc_crm.services.staffing_candidates import candidate_summaries, worker_timesheet_summary
from cc_crm.services.staffing_deadlines import DeadlineConfig
from cc_crm.services.staffing_disposition import disposition
from cc_crm.services.staffing_invoices import StaffingInvoiceService
from cc_crm.services.staffing_licenses import StaffingLicenseService
from cc_crm.services.staffing_overview import DISCLAIMER, overview, pair_deadlines
from cc_crm.services.staffing_prior_periods import StaffingPriorPeriodService
from cc_crm.services.staffing_settings import load_config, save_config
from cc_crm.services.staffing_takeover import StaffingTakeoverService
from cc_crm.services.staffing_takeover_fee import (
    FeeTier,
    load_tiers,
    months_between,
    save_tiers,
    tier_percent,
)
from cc_crm.services.staffing_tasks import build_tasks
from cc_crm.services.staffing_timesheets import StaffingTimesheetService
from cc_crm.services.staffing_visibility import (
    forbid_money_for_non_admin,
    redact,
    redact_invoice,
)
from cc_crm.services.staffing_workers import StaffingWorkerService, worker_read

router = APIRouter(prefix="/staffing")


def _check_owner(
    session: DatabaseSession, user: CurrentUser, owner_user_id: uuid.UUID | None
) -> None:
    """Ein Nicht-Admin darf Einsätze nur Disponenten seines Bereichs zuweisen (sonst verschwände
    der Einsatz aus seiner eigenen Sicht)."""
    scope = staffing_owner_scope(user, session)
    if scope is not None and owner_user_id is not None and owner_user_id not in scope:
        raise PermissionDeniedError("Dieser Disponent liegt ausserhalb Ihres Bereichs.")


# --- Übersicht, Fristen, Einstellungen --------------------------------------------------------


@router.get("/overview", response_model=StaffingOverviewRead)
def get_overview(session: DatabaseSession, current_user: CurrentUser) -> StaffingOverviewRead:
    return overview(session, staffing_owner_scope(current_user, session), date.today())


@router.get("/disposition", response_model=StaffingDispositionRead)
def get_disposition(session: DatabaseSession, current_user: CurrentUser) -> StaffingDispositionRead:
    """Disposition: Kennzahlen, Bench ("frei seit"), Stundenzettel-Eingang. Einsätze im
    Sichtbereich des Nutzers; kein Lohn, keine Marge."""
    return disposition(session, staffing_owner_scope(current_user, session), date.today())


@router.post("/candidate-summary", response_model=list[StaffingCandidateSummaryRead])
def staffing_candidate_summary(
    payload: StaffingCandidateSummaryRequest, session: DatabaseSession, current_user: CurrentUser
) -> list[StaffingCandidateSummaryRead]:
    """Sammelabfrage für die Spalte "Überlassung" der Kandidatenliste (eine Abfrage je Baustein,
    nicht je Kandidat): Status, aktueller Kunde, dringendste Frist. Kein Lohn, keine Marge."""
    summaries = candidate_summaries(session, payload.candidate_ids, date.today())
    return [summaries[cid] for cid in payload.candidate_ids]


@router.get("/workers/{worker_id}/timesheet-summary", response_model=StaffingWorkerTimesheetSummary)
def get_worker_timesheet_summary(
    worker_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> StaffingWorkerTimesheetSummary:
    """Stundenzettel einer Person nach Status (nur Einsätze im Besitzbereich des Nutzers)."""
    if StaffingWorkerRepository(session).get(worker_id) is None:
        raise EntityNotFoundError("Leiharbeitnehmer nicht gefunden")
    return worker_timesheet_summary(session, worker_id, staffing_owner_scope(current_user, session))


@router.get("/tasks", response_model=StaffingTasksRead)
def get_staffing_tasks(session: DatabaseSession, current_user: CurrentUser) -> StaffingTasksRead:
    """To-dos und Hinweise der Ansicht Überlassung (Fristen, Stundenzettel, Checklisten, Bench,
    Erlaubnis). Im Besitzbereich des Nutzers; kein Lohn, keine Marge."""
    return build_tasks(session, staffing_owner_scope(current_user, session), date.today())


@router.get("/deadlines", response_model=list[StaffingPairDeadlineRead])
def list_deadlines(
    session: DatabaseSession, current_user: CurrentUser
) -> list[StaffingPairDeadlineRead]:
    """Fristen je Paar (Leiharbeitnehmer, Kunde), dringendste zuerst."""
    return pair_deadlines(session, staffing_owner_scope(current_user, session), date.today())


def _settings_read(config: DeadlineConfig) -> StaffingSettingsRead:
    return StaffingSettingsRead(
        max_months=config.max_months,
        equal_pay_months=config.equal_pay_months,
        reset_gap_months=config.reset_gap_months,
        yellow_days=config.yellow_days,
        red_days=config.red_days,
        notice=DISCLAIMER,
    )


@router.get("/settings", response_model=StaffingSettingsRead)
def get_settings(session: DatabaseSession, _user: CurrentUser) -> StaffingSettingsRead:
    return _settings_read(load_config(session))


@router.put("/settings", response_model=StaffingSettingsRead)
def put_settings(
    payload: StaffingSettingsUpdate, session: DatabaseSession, _admin: AdminUser
) -> StaffingSettingsRead:
    return _settings_read(save_config(session, DeadlineConfig(**payload.model_dump())))


# --- Leiharbeitnehmer --------------------------------------------------------------------------


@router.get("/workers", response_model=list[StaffingWorkerRead])
def list_workers(
    session: DatabaseSession,
    current_user: CurrentUser,
    worker_status: Annotated[StaffingWorkerStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[StaffingWorkerRead]:
    rows = StaffingWorkerService(session).rows(status=worker_status, offset=offset, limit=limit)
    return [redact(worker_read(row), current_user) for row in rows]


@router.post("/workers", response_model=StaffingWorkerRead, status_code=status.HTTP_201_CREATED)
def create_worker(
    payload: StaffingWorkerCreate, session: DatabaseSession, current_user: CurrentUser
) -> StaffingWorkerRead:
    forbid_money_for_non_admin(payload, current_user)
    row = StaffingWorkerService(session).create(payload, current_user)
    return redact(worker_read(row), current_user)


@router.get("/workers/by-candidate/{candidate_id}", response_model=StaffingWorkerRead)
def get_worker_by_candidate(
    candidate_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> StaffingWorkerRead:
    row = StaffingWorkerService(session).row_for_candidate(candidate_id)
    if row is None:
        raise EntityNotFoundError("Kein Leiharbeitnehmer-Profil für diesen Kandidaten")
    return redact(worker_read(row), current_user)


@router.get("/workers/{worker_id}", response_model=StaffingWorkerRead)
def get_worker(
    worker_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> StaffingWorkerRead:
    return redact(worker_read(StaffingWorkerService(session).get_row(worker_id)), current_user)


@router.patch("/workers/{worker_id}", response_model=StaffingWorkerRead)
def update_worker(
    worker_id: uuid.UUID,
    payload: StaffingWorkerUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> StaffingWorkerRead:
    forbid_money_for_non_admin(payload, current_user)
    row = StaffingWorkerService(session).update(worker_id, payload, current_user)
    return redact(worker_read(row), current_user)


# --- Vorzeiten beim Kunden ---------------------------------------------------------------------
# Vorzeiten gehören zum Leiharbeitnehmer (gemeinsamer Pool wie die Person selbst), nicht zu einem
# Einsatz: gleiche Rechte wie die Leiharbeitnehmer-Routen, keine Lohn- oder Margenwerte.


@router.get("/workers/{worker_id}/prior-periods", response_model=list[StaffingPriorPeriodRead])
def list_prior_periods(
    worker_id: uuid.UUID, session: DatabaseSession, _user: CurrentUser
) -> list[StaffingPriorPeriodRead]:
    return StaffingPriorPeriodService(session).list_for_worker(worker_id)


@router.post(
    "/workers/{worker_id}/prior-periods",
    response_model=StaffingPriorPeriodRead,
    status_code=status.HTTP_201_CREATED,
)
def create_prior_period(
    worker_id: uuid.UUID,
    payload: StaffingPriorPeriodCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> StaffingPriorPeriodRead:
    return StaffingPriorPeriodService(session).create(worker_id, payload, current_user)


@router.patch("/prior-periods/{prior_period_id}", response_model=StaffingPriorPeriodRead)
def update_prior_period(
    prior_period_id: uuid.UUID,
    payload: StaffingPriorPeriodUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> StaffingPriorPeriodRead:
    return StaffingPriorPeriodService(session).update(prior_period_id, payload, current_user)


@router.delete("/prior-periods/{prior_period_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prior_period(
    prior_period_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> Response:
    """Löschen als Eingabekorrektur erlaubt; der Audit-Log hält den gelöschten Zeitraum fest."""
    StaffingPriorPeriodService(session).delete(prior_period_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Verträge ---------------------------------------------------------------------------------


@router.get("/contracts", response_model=list[StaffingContractRead])
def list_contracts(
    session: DatabaseSession,
    _user: CurrentUser,
    client_company_id: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[StaffingContractRead]:
    rows = StaffingContractService(session).contracts.rows(
        client_company_id=client_company_id, offset=offset, limit=limit
    )
    return [contract_read(row) for row in rows]


@router.post("/contracts", response_model=StaffingContractRead, status_code=status.HTTP_201_CREATED)
def create_contract(
    payload: StaffingContractCreate, session: DatabaseSession, current_user: CurrentUser
) -> StaffingContractRead:
    return contract_read(StaffingContractService(session).create(payload, current_user))


@router.get("/contracts/{contract_id}", response_model=StaffingContractRead)
def get_contract(
    contract_id: uuid.UUID, session: DatabaseSession, _user: CurrentUser
) -> StaffingContractRead:
    return contract_read(StaffingContractService(session).get_row(contract_id))


@router.patch("/contracts/{contract_id}", response_model=StaffingContractRead)
def update_contract(
    contract_id: uuid.UUID,
    payload: StaffingContractUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> StaffingContractRead:
    return contract_read(
        StaffingContractService(session).update(contract_id, payload, current_user)
    )


# --- Einsätze ---------------------------------------------------------------------------------


@router.get("/assignments", response_model=list[StaffingAssignmentRead])
def list_assignments(
    session: DatabaseSession,
    current_user: CurrentUser,
    assignment_status: Annotated[StaffingAssignmentStatus | None, Query(alias="status")] = None,
    worker_id: uuid.UUID | None = None,
    client_company_id: uuid.UUID | None = None,
    overdue: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[StaffingAssignmentRead]:
    """`overdue=true`: nur aktive Einsätze, deren geplantes Ende überschritten ist."""
    rows = StaffingAssignmentService(session).assignments.rows(
        owner_scope=staffing_owner_scope(current_user, session),
        status=assignment_status,
        worker_id=worker_id,
        client_company_id=client_company_id,
        overdue_on=date.today() if overdue else None,
        offset=offset,
        limit=limit,
    )
    return [redact(assignment_read(row), current_user) for row in rows]


@router.post(
    "/assignments", response_model=StaffingAssignmentRead, status_code=status.HTTP_201_CREATED
)
def create_assignment(
    payload: StaffingAssignmentCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
    confirm_engagement: bool = False,
) -> StaffingAssignmentRead:
    forbid_money_for_non_admin(payload, current_user)
    _check_owner(session, current_user, payload.owner_user_id)
    worker = session.get(StaffingWorker, payload.worker_id)
    if worker is not None:  # unbekannte Leiharbeitnehmer meldet der Service wie bisher
        ensure_no_conflict(
            session, current_user, worker.candidate_id, "staffing", confirm_engagement
        )
    row = StaffingAssignmentService(session).create(payload, current_user)
    return redact(assignment_read(row), current_user)


@router.get(
    "/assignments/{assignment_id}",
    dependencies=[AssignmentAccess],
    response_model=StaffingAssignmentDetail,
)
def get_assignment(
    assignment_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> StaffingAssignmentDetail:
    return redact(StaffingAssignmentService(session).detail(assignment_id), current_user)


@router.patch(
    "/assignments/{assignment_id}",
    dependencies=[AssignmentAccess],
    response_model=StaffingAssignmentDetail,
)
def update_assignment(
    assignment_id: uuid.UUID,
    payload: StaffingAssignmentUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> StaffingAssignmentDetail:
    forbid_money_for_non_admin(payload, current_user)
    _check_owner(session, current_user, payload.owner_user_id)
    service = StaffingAssignmentService(session)
    service.update(assignment_id, payload, current_user)
    return redact(service.detail(assignment_id), current_user)


@router.post(
    "/assignments/{assignment_id}/status",
    dependencies=[AssignmentAccess],
    response_model=StaffingAssignmentDetail,
)
def change_assignment_status(
    assignment_id: uuid.UUID,
    payload: StaffingAssignmentStatusChange,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> StaffingAssignmentDetail:
    """Aktivierung nur mit gültiger AÜG-Erlaubnis und vollständiger Pflicht-Checkliste."""
    StaffingActivationService(session).change_status(assignment_id, payload, current_user)
    return redact(StaffingAssignmentService(session).detail(assignment_id), current_user)


@router.patch(
    "/assignments/{assignment_id}/checklist/{item_id}",
    dependencies=[AssignmentAccess],
    response_model=StaffingAssignmentDetail,
)
def update_checklist_item(
    assignment_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: StaffingChecklistItemUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> StaffingAssignmentDetail:
    detail = StaffingAssignmentService(session).update_checklist_item(
        assignment_id, item_id, payload, current_user
    )
    return redact(detail, current_user)


# --- Erlaubnis ---------------------------------------------------------------------------------


@router.get("/licenses", response_model=list[StaffingLicenseRead])
def list_licenses(session: DatabaseSession, _user: CurrentUser) -> list[StaffingLicenseRead]:
    return [
        StaffingLicenseRead.model_validate(lic) for lic in StaffingLicenseService(session).list()
    ]


@router.post("/licenses", response_model=StaffingLicenseRead, status_code=status.HTTP_201_CREATED)
def create_license(
    payload: StaffingLicenseCreate, session: DatabaseSession, admin: AdminUser
) -> StaffingLicenseRead:
    return StaffingLicenseRead.model_validate(
        StaffingLicenseService(session).create(payload, admin)
    )


@router.patch("/licenses/{license_id}", response_model=StaffingLicenseRead)
def update_license(
    license_id: uuid.UUID,
    payload: StaffingLicenseUpdate,
    session: DatabaseSession,
    admin: AdminUser,
) -> StaffingLicenseRead:
    return StaffingLicenseRead.model_validate(
        StaffingLicenseService(session).update(license_id, payload, admin)
    )


# --- Stundenzettel -----------------------------------------------------------------------------
# Stundenzettel gehoeren zu einem Einsatz und folgen dessen Sichtbarkeit: `AssignmentAccess`
# (Pfad mit assignment_id) bzw. `TimesheetAccess` (Pfad mit timesheet_id). Die Kundenfreigabe per
# Link steht ohne Login in api/v1/staffing_public.py.


@router.get(
    "/assignments/{assignment_id}/timesheets",
    dependencies=[AssignmentAccess],
    response_model=list[StaffingTimesheetRead],
)
def list_timesheets(
    assignment_id: uuid.UUID, session: DatabaseSession, _user: CurrentUser
) -> list[StaffingTimesheetRead]:
    return StaffingTimesheetService(session).list_for_assignment(assignment_id)


@router.post(
    "/assignments/{assignment_id}/timesheets",
    dependencies=[AssignmentAccess],
    response_model=StaffingTimesheetRead,
    status_code=status.HTTP_201_CREATED,
)
def create_timesheet(
    assignment_id: uuid.UUID,
    payload: StaffingTimesheetCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> StaffingTimesheetRead:
    return StaffingTimesheetService(session).create(assignment_id, payload, current_user)


@router.get(
    "/timesheets/{timesheet_id}",
    dependencies=[TimesheetAccess],
    response_model=StaffingTimesheetRead,
)
def get_timesheet(
    timesheet_id: uuid.UUID, session: DatabaseSession, _user: CurrentUser
) -> StaffingTimesheetRead:
    return StaffingTimesheetService(session).get_read(timesheet_id)


@router.put(
    "/timesheets/{timesheet_id}/entries",
    dependencies=[TimesheetAccess],
    response_model=StaffingTimesheetRead,
)
def set_timesheet_entries(
    timesheet_id: uuid.UUID,
    payload: StaffingTimesheetEntriesUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> StaffingTimesheetRead:
    return StaffingTimesheetService(session).set_entries(timesheet_id, payload, current_user)


@router.post(
    "/timesheets/{timesheet_id}/submit",
    dependencies=[TimesheetAccess],
    response_model=StaffingTimesheetSubmitResult,
)
def submit_timesheet(
    timesheet_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> StaffingTimesheetSubmitResult:
    """Einreichen und den Freigabelink für den Kunden erzeugen (erneuter Aufruf = neuer Link,
    der alte wird ungültig). Der Link steht nur in dieser Antwort."""
    return StaffingTimesheetService(session).submit(timesheet_id, current_user)


# --- Direct -> Überlassung: als Einsatz anbieten -------------------------------------------


@router.post("/offer-from-candidate", response_model=StaffingOfferResult)
def offer_candidate_as_assignment(
    payload: StaffingOfferInput,
    session: DatabaseSession,
    current_user: CurrentUser,
    confirm_engagement: bool = False,
) -> StaffingOfferResult:
    """Legt das Leiharbeitnehmer-Profil (Anwärter) und optional einen geplanten Einsatz an. Ist der
    Kandidat schon im Austausch, greift der Hinweis (409, mit Bestätigung) bzw. die Sperre."""
    _check_owner(session, current_user, payload.owner_user_id)
    ensure_no_conflict(session, current_user, payload.candidate_id, "staffing", confirm_engagement)
    workers = StaffingWorkerService(session)
    existing = StaffingWorkerRepository(session).by_candidate(payload.candidate_id)
    created = existing is None
    if existing is None:
        worker_id = workers.create(
            StaffingWorkerCreate(candidate_id=payload.candidate_id), current_user
        ).worker.id
    else:
        worker_id = existing.id
    assignment_id = None
    if payload.client_company_id is not None and payload.start_date is not None:
        row = StaffingAssignmentService(session).create(
            StaffingAssignmentCreate(
                worker_id=worker_id,
                client_company_id=payload.client_company_id,
                owner_user_id=payload.owner_user_id,
                start_date=payload.start_date,
                planned_end_date=payload.planned_end_date,
            ),
            current_user,
        )
        assignment_id = row.assignment.id
    return StaffingOfferResult(
        worker_id=worker_id, worker_created=created, assignment_id=assignment_id
    )


# --- Übernahme durch den Kunden ----------------------------------------------------------------


@router.post(
    "/assignments/{assignment_id}/takeover",
    dependencies=[AssignmentAccess],
    response_model=StaffingTakeoverResult,
)
def take_over_assignment(
    assignment_id: uuid.UUID,
    payload: StaffingTakeoverInput,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> StaffingTakeoverResult:
    """Beendet den Einsatz und legt einen Vermittlungsprozess mit Honorar an (siehe
    services/staffing_takeover.py)."""
    result = StaffingTakeoverService(session).take_over(assignment_id, payload, current_user)
    return result.model_copy(update={"assignment": redact(result.assignment, current_user)})


@router.get(
    "/assignments/{assignment_id}/takeover-preview",
    dependencies=[AssignmentAccess],
    response_model=StaffingTakeoverPreview,
)
def preview_takeover(
    assignment_id: uuid.UUID, session: DatabaseSession, takeover_date: date | None = None
) -> StaffingTakeoverPreview:
    """Wie wirkt die Staffel der Übernahme-Fee bei diesem Einsatz (Monate, Anteil, Honorarsatz)."""
    assignment = StaffingAssignmentService(session).get_row(assignment_id).assignment
    client = session.get(ClientCompany, assignment.client_company_id)
    months = months_between(assignment.start_date, takeover_date or date.today())
    tier = tier_percent(months, load_tiers(session))
    base = client.fee_percentage if client is not None else None
    return StaffingTakeoverPreview(
        months_worked=months,
        tier_percent=tier,
        base_fee_percentage=base,
        effective_fee_percentage=(
            None if base is None else (base * tier / Decimal("100")).quantize(Decimal("0.01"))
        ),
    )


def _tiers_read(session: Session) -> TakeoverFeeTiersRead:
    return TakeoverFeeTiersRead(
        tiers=[
            TakeoverFeeTierRead(up_to_months=t.up_to_months, percent_of_fee=t.percent_of_fee)
            for t in load_tiers(session)
        ],
        notice=(
            "Platzhalter-Staffel, nicht abgestimmt: mit der vertraglich vereinbarten Staffel "
            "abgleichen. Kein Rechtsrat."
        ),
    )


@router.get("/takeover-fee-tiers", response_model=TakeoverFeeTiersRead)
def get_takeover_fee_tiers(session: DatabaseSession, _user: CurrentUser) -> TakeoverFeeTiersRead:
    return _tiers_read(session)


@router.put("/takeover-fee-tiers", response_model=TakeoverFeeTiersRead)
def put_takeover_fee_tiers(
    payload: TakeoverFeeTiersUpdate, session: DatabaseSession, admin: AdminUser
) -> TakeoverFeeTiersRead:
    save_tiers(
        session,
        [FeeTier(t.up_to_months, t.percent_of_fee) for t in payload.tiers],
        admin.email,
        admin.id,
    )
    return _tiers_read(session)


# --- Abrechnung und Export -----------------------------------------------------------------------
# Rechnungen folgen dem Rechnungs- und Freigabemodell der Vermittlung
# (services/staffing_invoices.py). Beträge sind Margendaten: Nicht-Admins sehen sie nie, können
# aber Entwuerfe aus Stundenzetteln ihres Bereichs erstellen und das Stellen über die
# Freigabe-Inbox beantragen.


@router.get("/billable-timesheets", response_model=list[StaffingBillableTimesheetRead])
def list_billable_timesheets(
    session: DatabaseSession, current_user: CurrentUser
) -> list[StaffingBillableTimesheetRead]:
    return StaffingInvoiceService(session).billable_timesheets(
        staffing_owner_scope(current_user, session)
    )


@router.get("/invoices", response_model=list[StaffingInvoiceRead])
def list_invoices(session: DatabaseSession, current_user: CurrentUser) -> list[StaffingInvoiceRead]:
    invoices = StaffingInvoiceService(session).list_invoices(
        staffing_owner_scope(current_user, session)
    )
    return [redact_invoice(invoice, current_user) for invoice in invoices]


@router.post("/invoices", response_model=StaffingInvoiceRead, status_code=status.HTTP_201_CREATED)
def create_invoice_draft(
    payload: StaffingInvoiceCreate, session: DatabaseSession, current_user: CurrentUser
) -> StaffingInvoiceRead:
    invoice = StaffingInvoiceService(session).create_draft(
        payload, current_user, staffing_owner_scope(current_user, session)
    )
    return redact_invoice(invoice, current_user)


@router.get(
    "/invoices/{invoice_id}", dependencies=[InvoiceAccess], response_model=StaffingInvoiceRead
)
def get_invoice(
    invoice_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> StaffingInvoiceRead:
    return redact_invoice(StaffingInvoiceService(session).get_read(invoice_id), current_user)


@router.post(
    "/invoices/{invoice_id}/status",
    dependencies=[InvoiceAccess],
    response_model=StaffingInvoiceStatusResult,
)
def change_invoice_status(
    invoice_id: uuid.UUID,
    payload: InvoiceStatusChange,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> StaffingInvoiceStatusResult:
    """Wie bei Vermittlungsrechnungen: "Rechnung stellen" durch einen Nicht-Admin wird zur
    Freigabe-Anfrage (`approval_request`), Admins stellen direkt."""
    service = StaffingInvoiceService(session)
    _invoice, approval = service.change_status(invoice_id, payload, current_user)
    return StaffingInvoiceStatusResult(
        invoice=redact_invoice(service.get_read(invoice_id), current_user),
        approval_request=(
            ApprovalRequestRead.model_validate(approval).model_copy(
                update={"entity_label": ApprovalService(session).entity_label(approval)}
            )
            if approval is not None
            else None
        ),
    )


@router.get("/export/hours.csv")
def export_hours_csv(
    period_start: date, period_end: date, session: DatabaseSession, _admin: AdminUser
) -> Response:
    """Stunden je Leiharbeitnehmer und Kunde für die Lohnabrechnung (nur Admins - enthält den
    Stundenlohn). Nur vom Kunden freigegebene Stunden. Format: docs/UEBERLASSUNG.md."""
    content = StaffingInvoiceService(session).export_hours_csv(period_start, period_end)
    filename = f"stunden_{period_start:%Y%m%d}_{period_end:%Y%m%d}.csv"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
