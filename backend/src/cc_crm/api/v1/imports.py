from typing import Annotated

from fastapi import APIRouter, Query, Response

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.schemas.imports import (
    ImportCommitRequest,
    ImportEntity,
    ImportFilePayload,
    ImportPreview,
    ImportResult,
)
from cc_crm.services.imports import ImportService

router = APIRouter(prefix="/import")


@router.get("/candidates/export")
def export_candidates(
    session: DatabaseSession,
    file_format: Annotated[str, Query(pattern="^(csv|xlsx)$")] = "xlsx",
) -> Response:
    """Voll befuellter Export ALLER Kandidaten (Master-Excel) - Ausgangspunkt
    fuer eine Bulk-Korrektur bestehender Daten ueber denselben Import-Wizard
    (siehe ImportService.commit fuer die candidate_number-Feld-Update-
    Logik)."""
    content, filename, media_type = ImportService(session).export_candidates(file_format)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/{entity}/template")
def download_template(
    entity: ImportEntity,
    session: DatabaseSession,
    file_format: Annotated[str, Query(pattern="^(csv|xlsx)$")] = "csv",
) -> Response:
    content, filename, media_type = ImportService(session).template(entity, file_format)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=content, media_type=media_type, headers=headers)


@router.post("/{entity}/preview", response_model=ImportPreview)
def preview_import(
    entity: ImportEntity, payload: ImportFilePayload, session: DatabaseSession
) -> ImportPreview:
    return ImportService(session).preview(entity, payload)


@router.post("/{entity}/commit", response_model=ImportResult)
def commit_import(
    entity: ImportEntity, payload: ImportCommitRequest, session: DatabaseSession
) -> ImportResult:
    return ImportService(session).commit(entity, payload.rows, payload.confirmed)
