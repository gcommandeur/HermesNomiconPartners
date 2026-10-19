# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Meine Provision: jeder Angemeldete sieht sich selbst, Teamleiter ihr Team, Admins alle.
Bewusst NICHT hinter der Ansicht "Gesamt" (`/commission` ist der Admin-Bericht mit Margen)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.schemas.my_commission import (
    MyCommissionPerson,
    MyCommissionRead,
    MyCommissionTimeline,
)
from cc_crm.services import commission_timeline, my_commission
from cc_crm.services.commission_report import current_quarter

router = APIRouter(prefix="/my-commission")


@router.get("", response_model=MyCommissionRead)
def get_my_commission(
    session: DatabaseSession,
    current_user: CurrentUser,
    user_id: Annotated[uuid.UUID | None, Query()] = None,
    year: Annotated[int | None, Query(ge=2000, le=2200)] = None,
    quarter: Annotated[int | None, Query(ge=1, le=4)] = None,
) -> MyCommissionRead:
    """Provision einer Person im Quartal (Standard: ich selbst, laufendes Quartal). Fremde oder
    nicht vorhandene `user_id`: 404."""
    default_year, default_quarter = current_quarter()
    return my_commission.build(
        session, current_user, user_id, year or default_year, quarter or default_quarter
    )


@router.get("/timeline", response_model=MyCommissionTimeline)
def get_timeline(
    session: DatabaseSession,
    current_user: CurrentUser,
    user_id: Annotated[uuid.UUID | None, Query()] = None,
) -> MyCommissionTimeline:
    """Zeitstrahl der letzten 12 Monate, Monatswert, laufendes Quartal und Fortschritt zur nächsten
    Rolle. Gleiche Rechte wie `GET /my-commission`: fremd oder nicht vorhanden = 404."""
    return commission_timeline.build_timeline(session, current_user, user_id)


@router.get("/people", response_model=list[MyCommissionPerson])
def get_people(session: DatabaseSession, current_user: CurrentUser) -> list[MyCommissionPerson]:
    """Personen, die ich ansehen darf: ich selbst, als Teamleiter mein Team, als Admin alle."""
    return my_commission.people(session, current_user)
