from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from cc_crm.api.dependencies import DatabaseSession

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    service: str
    detail: str | None = None


@router.get("/health", response_model=HealthResponse)
def health(session: DatabaseSession, response: Response) -> HealthResponse:
    """Prueft zusaetzlich zum reinen Prozess-Status, ob die Datenbank
    tatsaechlich erreichbar ist ("SELECT 1") - ohne das wuerde ein Hosting-
    Anbieter (z.B. Railway) einen Deploy mit kaputter DB-Verbindung
    faelschlich als gesund einstufen (siehe Nutzer-Feedback vor Go-Live,
    besonders relevant beim bevorstehenden Wechsel auf Postgres). Kein
    Roh-Traceback nach aussen - nur eine knappe, generische Meldung."""
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - DB-Fehlerklassen sind treiberabhaengig (sqlite3/psycopg)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="error", service="cc-crm-api", detail="Datenbank nicht erreichbar"
        )
    return HealthResponse(status="ok", service="cc-crm-api")


@router.get("/readyz", response_model=HealthResponse)
def readyz(session: DatabaseSession, response: Response) -> HealthResponse:
    """Bereit fuer Verkehr: Datenbank erreichbar UND Schema auf dem Stand des
    Codes (`alembic_version` = neueste Migration). Ein Deploy, dessen Migration
    noch nicht gelaufen ist, soll keinen Verkehr bekommen. `/health` bleibt die
    einfache Lebendigkeitspruefung."""
    from cc_crm.core.migrations import script_head

    try:
        current = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # noqa: BLE001 - treiberabhaengige Fehlerklassen
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="error", service="cc-crm-api", detail="Datenbank nicht bereit"
        )
    head = script_head()
    if head is None or current != head:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="error", service="cc-crm-api", detail="Datenbank-Schema veraltet"
        )
    return HealthResponse(status="ok", service="cc-crm-api")
