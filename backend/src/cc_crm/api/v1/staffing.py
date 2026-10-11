# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Arbeitnehmerueberlassung: Leiharbeitnehmer, Vertraege, Einsaetze, Erlaubnis, Fristen.

Rechte: Einsaetze sind ueber den Disponenten gescopt (api/staffing_dependencies.py), jede Route
mit `assignment_id` im Pfad hat `AssignmentAccess`. Lohn und Verrechnungssatz sehen und setzen nur
Admins (services/staffing_visibility.py); Erlaubnis und Einstellungen aendern nur Admins."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from cc_crm.api.dependencies import AdminUser, CurrentUser, DatabaseSession
from cc_crm.api.staffing_dependencies import AssignmentAccess, staffing_owner_scope
from cc_crm.core.errors import EntityNotFoundError, PermissionDeniedError
from cc_crm.models.staffing import StaffingAssignmentStatus, StaffingWorkerStatus
from cc_crm.schemas.staffing import (
    StaffingAssignmentCreate,
    StaffingAssignmentDetail,
    StaffingAssignmentRead,
    StaffingAssignmentStatusChange,
    StaffingAssignmentUpdate,
    StaffingChecklistItemUpdate,
    StaffingContractCreate,
    StaffingContractRead,
    StaffingContractUpdate,
    StaffingLicenseCreate,
    StaffingLicenseRead,
    StaffingLicenseUpdate,
    StaffingOverviewRead,
    StaffingPairDeadlineRead,
    StaffingSettingsRead,
    StaffingSettingsUpdate,
    StaffingWorkerCreate,
    StaffingWorkerRead,
    StaffingWorkerUpdate,
)
from cc_crm.services.staffing_activation import StaffingActivationService
from cc_crm.services.staffing_assignments import (
    StaffingAssignmentService,
    StaffingContractService,
    assignment_read,
    contract_read,
)
from cc_crm.services.staffing_deadlines import DeadlineConfig
from cc_crm.services.staffing_licenses import StaffingLicenseService
from cc_crm.services.staffing_overview import DISCLAIMER, overview, pair_deadlines
from cc_crm.services.staffing_settings import load_config, save_config
from cc_crm.services.staffing_visibility import forbid_money_for_non_admin, redact
from cc_crm.services.staffing_workers import StaffingWorkerService, worker_read

router = APIRouter(prefix="/staffing")


def _check_owner(
    session: DatabaseSession, user: CurrentUser, owner_user_id: uuid.UUID | None
) -> None:
    """Ein Nicht-Admin darf Einsaetze nur Disponenten seines Bereichs zuweisen (sonst verschwaende
    der Einsatz aus seiner eigenen Sicht)."""
    scope = staffing_owner_scope(user, session)
    if scope is not None and owner_user_id is not None and owner_user_id not in scope:
        raise PermissionDeniedError("Dieser Disponent liegt ausserhalb Ihres Bereichs.")


# --- Uebersicht, Fristen, Einstellungen --------------------------------------------------------


@router.get("/overview", response_model=StaffingOverviewRead)
def get_overview(session: DatabaseSession, current_user: CurrentUser) -> StaffingOverviewRead:
    return overview(session, staffing_owner_scope(current_user, session), date.today())


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
        raise EntityNotFoundError("Kein Leiharbeitnehmer-Profil fuer diesen Kandidaten")
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


# --- Vertraege ---------------------------------------------------------------------------------


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


# --- Einsaetze ---------------------------------------------------------------------------------


@router.get("/assignments", response_model=list[StaffingAssignmentRead])
def list_assignments(
    session: DatabaseSession,
    current_user: CurrentUser,
    assignment_status: Annotated[StaffingAssignmentStatus | None, Query(alias="status")] = None,
    worker_id: uuid.UUID | None = None,
    client_company_id: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[StaffingAssignmentRead]:
    rows = StaffingAssignmentService(session).assignments.rows(
        owner_scope=staffing_owner_scope(current_user, session),
        status=assignment_status,
        worker_id=worker_id,
        client_company_id=client_company_id,
        offset=offset,
        limit=limit,
    )
    return [redact(assignment_read(row), current_user) for row in rows]


@router.post(
    "/assignments", response_model=StaffingAssignmentRead, status_code=status.HTTP_201_CREATED
)
def create_assignment(
    payload: StaffingAssignmentCreate, session: DatabaseSession, current_user: CurrentUser
) -> StaffingAssignmentRead:
    forbid_money_for_non_admin(payload, current_user)
    _check_owner(session, current_user, payload.owner_user_id)
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
    """Aktivierung nur mit gueltiger AÜG-Erlaubnis und vollstaendiger Pflicht-Checkliste."""
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
