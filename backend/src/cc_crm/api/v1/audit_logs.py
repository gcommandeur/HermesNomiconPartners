from typing import Annotated

from fastapi import APIRouter, Query

from cc_crm.api.dependencies import AdminUser, DatabaseSession
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.schemas.recruiting import AuditLogRead

router = APIRouter(prefix="/audit-logs")


@router.get("", response_model=list[AuditLogRead])
def list_audit_logs(
    session: DatabaseSession,
    _admin: AdminUser,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[AuditLogRead]:
    """Admin-only, chronologische Liste (neueste zuerst) - siehe Punkt 2 des
    Auftrags. Bewusst keine Filterung, eine einfache Zeitleiste reicht."""
    entries = AuditLogRepository(session).list_recent(offset=offset, limit=limit)
    return [AuditLogRead.model_validate(entry) for entry in entries]
