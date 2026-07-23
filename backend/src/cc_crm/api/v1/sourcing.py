import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query
from sqlalchemy import select

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import SourcingLeadStatus, SourcingSourceType
from cc_crm.schemas.pagination import Page
from cc_crm.schemas.sourcing import SourcingLeadRead, SourcingRunRequest, SourcingRunResult
from cc_crm.services.sourcing import SourcingService, scan_team_pages_in_background

router = APIRouter(prefix="/sourcing")


@router.post("/run", response_model=SourcingRunResult)
def run_sourcing(
    payload: SourcingRunRequest,
    session: DatabaseSession,
    background_tasks: BackgroundTasks,
) -> SourcingRunResult:
    """Manuell ausgeloester Sourcing-Lauf (kein Cron) - synchron, damit die
    Antwort direkt die Zahlen (gefunden/neu/uebersprungen) enthaelt (~2s pro
    Gebiet/Kanzlei, das Frontend ruft mit verlaengertem Timeout auf).
    Einzige Ausnahme: scan_all_companies laeuft als FastAPI-BackgroundTask,
    da hunderte Kanzlei-Websites + LLM-Aufrufe jeden HTTP-Timeout sprengen -
    die Antwort meldet dann nur die Anzahl gestarteter Kanzlei-Scans."""
    service = SourcingService(session)
    if payload.source_type == SourcingSourceType.KANZLEI_TEAM_PAGE:
        if payload.scan_all_companies:
            company_ids = list(
                session.scalars(
                    select(ClientCompany.id).where(
                        ClientCompany.website.isnot(None), ClientCompany.website != ""
                    )
                ).all()
            )
            background_tasks.add_task(scan_team_pages_in_background, company_ids)
            return SourcingRunResult(background_started=len(company_ids))
        assert payload.client_company_ids is not None  # per Schema-Validierung
        return service.run_team_scrapes(payload.client_company_ids)
    assert payload.plz_or_ort is not None  # per Schema-Validierung
    return service.run_area_searches(payload.source_type, payload.plz_or_ort)


@router.get("/leads", response_model=Page[SourcingLeadRead])
def list_sourcing_leads(
    session: DatabaseSession,
    lead_status: Annotated[SourcingLeadStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Page[SourcingLeadRead]:
    leads, total = SourcingService(session).list_leads(
        status=lead_status, offset=offset, limit=limit
    )
    items = [SourcingLeadRead.model_validate(lead) for lead in leads]
    return Page(items=items, total_count=total, limit=limit, offset=offset)


@router.post("/leads/{lead_id}/approve", response_model=SourcingLeadRead)
def approve_sourcing_lead(
    lead_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> SourcingLeadRead:
    """Uebernimmt den Lead als echten Kandidaten (menschliche Bestaetigung -
    erst hier verlassen die Daten die Review-Ebene, siehe SourcingService)."""
    return SourcingLeadRead.model_validate(
        SourcingService(session).approve_lead(lead_id, current_user.id)
    )


@router.post("/leads/{lead_id}/reject", response_model=SourcingLeadRead)
def reject_sourcing_lead(
    lead_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> SourcingLeadRead:
    return SourcingLeadRead.model_validate(
        SourcingService(session).reject_lead(lead_id, current_user.id)
    )
