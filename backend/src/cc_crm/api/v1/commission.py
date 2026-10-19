# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie. ALLE Routen nur fuer Admins.
"""Provisionsmodell: Einstellungen, Quartalsbericht mit Break-even und Ampel, Rangzuordnung.

Es sind Gehalts- und Margendaten einzelner Mitarbeiter: jede Route verlangt `AdminUser`
(403 fuer alle anderen)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from cc_crm.api.dependencies import AdminUser, DatabaseSession
from cc_crm.schemas.commission import (
    CommissionConfigRead,
    CommissionConfigUpdate,
    CommissionReportRead,
    CommissionUserRankRead,
    CommissionUserRankUpdate,
)
from cc_crm.services.commission_report import (
    build_report,
    config_read,
    current_quarter,
    list_user_ranks,
    set_user_rank,
    update_config,
)
from cc_crm.services.commission_settings import load_config

router = APIRouter(prefix="/commission")


@router.get("/config", response_model=CommissionConfigRead)
def get_config(session: DatabaseSession, _admin: AdminUser) -> CommissionConfigRead:
    return config_read(load_config(session))


@router.put("/config", response_model=CommissionConfigRead)
def put_config(
    payload: CommissionConfigUpdate, session: DatabaseSession, admin: AdminUser
) -> CommissionConfigRead:
    return update_config(session, payload, admin)


@router.get("/report", response_model=CommissionReportRead)
def get_report(
    session: DatabaseSession,
    _admin: AdminUser,
    year: Annotated[int | None, Query(ge=2000, le=2200)] = None,
    quarter: Annotated[int | None, Query(ge=1, le=4)] = None,
) -> CommissionReportRead:
    """Quartalsbericht je Mitarbeiter (Standard: das laufende Quartal)."""
    default_year, default_quarter = current_quarter()
    return build_report(session, year or default_year, quarter or default_quarter)


@router.get("/users", response_model=list[CommissionUserRankRead])
def get_user_ranks(session: DatabaseSession, _admin: AdminUser) -> list[CommissionUserRankRead]:
    return list_user_ranks(session)


@router.put("/users/{user_id}/rank", response_model=CommissionUserRankRead)
def put_user_rank(
    user_id: uuid.UUID,
    payload: CommissionUserRankUpdate,
    session: DatabaseSession,
    admin: AdminUser,
) -> CommissionUserRankRead:
    return set_user_rank(session, user_id, payload, admin)
