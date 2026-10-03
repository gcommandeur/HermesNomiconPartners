import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import SourcingLeadStatus, SourcingSourceType
from cc_crm.schemas.pagination import Page
from cc_crm.schemas.sourcing import (
    SourcingLeadRead,
    SourcingRunRequest,
    SourcingRunResult,
    SourcingRunStatusRead,
)
from cc_crm.services.job_queue import enqueue
from cc_crm.services.sourcing import SourcingService

router = APIRouter(prefix="/sourcing")


def _enqueue_team_pages(
    session: DatabaseSession, company_ids: list[uuid.UUID], run_id: uuid.UUID
) -> None:
    # Ein Versuch: ein Wiederholungslauf wuerde den ganzen Scan von vorn starten.
    enqueue(
        session,
        "sourcing.team_pages",
        {"company_ids": [str(value) for value in company_ids], "run_id": str(run_id)},
        max_attempts=1,
    )


@router.post("/run", response_model=SourcingRunResult)
def run_sourcing(
    payload: SourcingRunRequest,
    session: DatabaseSession,
) -> SourcingRunResult:
    """Manuell ausgeloester Sourcing-Lauf (kein Cron) - synchron, damit die
    Antwort direkt die Zahlen (gefunden/neu/uebersprungen) enthaelt (~2s pro
    Gebiet/Kanzlei, das Frontend ruft mit verlaengertem Timeout auf).
    Einzige Ausnahme: scan_all_companies laeuft als Job der Warteschlange (services/job_queue.py),
    da hunderte Kanzlei-Websites + LLM-Aufrufe jeden HTTP-Timeout sprengen -
    die Antwort meldet dann nur die Anzahl gestarteter Kanzlei-Scans."""
    service = SourcingService(session)
    if payload.is_radius_search:
        assert payload.center is not None and payload.radius_km is not None
        if payload.source_type == SourcingSourceType.KANZLEI_TEAM_PAGE:
            company_ids = service.company_ids_around(payload.center, payload.radius_km)
            run = service.start_run(payload.source_type, total=len(company_ids))
            _enqueue_team_pages(session, company_ids, run.id)
            return SourcingRunResult(background_started=len(company_ids), run_id=run.id)
        postal_codes = service.postal_codes_around(payload.center, payload.radius_km)
        run = service.start_run(payload.source_type, total=len(postal_codes))
        enqueue(
            session,
            "sourcing.areas",
            {
                "source_type": payload.source_type.value,
                "postal_codes": postal_codes,
                "run_id": str(run.id),
            },
            max_attempts=1,
        )
        return SourcingRunResult(background_started=len(postal_codes), run_id=run.id)
    if payload.source_type == SourcingSourceType.KANZLEI_TEAM_PAGE:
        if payload.scan_all_companies:
            company_ids = list(
                session.scalars(
                    select(ClientCompany.id).where(
                        ClientCompany.website.isnot(None), ClientCompany.website != ""
                    )
                ).all()
            )
            run = service.start_run(payload.source_type, total=len(company_ids))
            _enqueue_team_pages(session, company_ids, run.id)
            return SourcingRunResult(background_started=len(company_ids), run_id=run.id)
        assert payload.client_company_ids is not None  # per Schema-Validierung
        return service.run_team_scrapes(payload.client_company_ids)
    assert payload.plz_or_ort is not None  # per Schema-Validierung
    return service.run_area_searches(payload.source_type, payload.plz_or_ort)


@router.get("/status", response_model=SourcingRunStatusRead | None)
def get_sourcing_run_status(session: DatabaseSession) -> SourcingRunStatusRead | None:
    """Stand des Hintergrund-Laufs "alle Kanzleien scannen" fuer die
    Lauf-Anzeige/Stop-Button im Frontend - null, wenn noch nie ein Lauf
    gestartet wurde."""
    run = SourcingService(session).get_run_status()
    return SourcingRunStatusRead.model_validate(run) if run is not None else None


@router.post("/stop", response_model=SourcingRunStatusRead)
def stop_sourcing_run(session: DatabaseSession) -> SourcingRunStatusRead:
    """Signalisiert dem laufenden Hintergrund-Lauf, nach der aktuellen
    Kanzlei abzubrechen (siehe scan_team_pages_in_background)."""
    return SourcingRunStatusRead.model_validate(SourcingService(session).request_stop())


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
