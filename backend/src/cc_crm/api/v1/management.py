# NOMICON: Ansicht "Gesamt" (Geschaeftsfuehrung) - nur Admins (Router-Abhaengigkeit "management").
from datetime import date

from fastapi import APIRouter

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.api.view_dependencies import ManagementViewUser
from cc_crm.schemas.management import ManagementOverviewRead, Period
from cc_crm.services import management_report

router = APIRouter(prefix="/management")


@router.get("/overview", response_model=ManagementOverviewRead)
def get_management_overview(
    session: DatabaseSession, _admin: ManagementViewUser, period: Period = "month"
) -> ManagementOverviewRead:
    return management_report.overview(session, period, date.today())
