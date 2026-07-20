import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.core.config import get_settings
from cc_crm.schemas.operational import (
    CockpitRead,
    DocumentCreate,
    DocumentRead,
    EmailDraftCreate,
    EmailDraftRead,
    EmailTemplateRead,
    ProfileSuggestion,
    SourcingMetricCreate,
    SourcingMetricRead,
)
from cc_crm.services.operational import (
    CockpitService,
    DocumentService,
    EmailWorkflowService,
    SourcingMetricService,
)
from cc_crm.services.storage import read_document_bytes, save_document_bytes

router = APIRouter()

# Whitelist fuer Dokumenten-Uploads (siehe upload_document unten) - orientiert
# an den tatsaechlich im Projekt genutzten Dokumenttypen (CV, Vertrag: PDF/
# Word/gescannte Bilder). Endung UND Content-Type werden geprueft - beides
# kann vom Client gefaelscht werden, aber ohne echtes Content-Sniffing ist das
# ein sinnvoller Kompromiss, der zumindest versehentliche/grob falsche
# Uploads (falscher Dateityp, keine Absicht zu taeuschen) zuverlaessig faengt.
_ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"}
_ALLOWED_UPLOAD_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "image/jpeg",
    "image/png",
}
_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB pro Lese-Schritt


def _validate_upload_type(file: UploadFile) -> None:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Dateityp nicht erlaubt. Erlaubt sind: PDF, DOCX, DOC, JPG, PNG.",
        )
    if file.content_type not in _ALLOWED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Dateityp nicht erlaubt (Content-Type passt nicht zur Dateiendung). "
                "Erlaubt sind: PDF, DOCX, DOC, JPG, PNG."
            ),
        )


async def _read_upload_with_size_limit(file: UploadFile, max_bytes: int) -> bytes:
    """Liest die Datei in 1-MB-Schritten statt sie mit einem einzigen
    `await file.read()` komplett unbegrenzt in den RAM zu laden - bricht
    sofort mit 413 ab, sobald das Limit ueberschritten wird, statt erst die
    komplette (evtl. riesige) Datei einzulesen und danach zu pruefen."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Datei ist zu groß (Limit: {max_bytes // (1024 * 1024)} MB).",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("/cockpit", response_model=CockpitRead)
def get_cockpit(
    session: DatabaseSession,
    period: Annotated[Literal["week", "month", "quarter"], Query()] = "week",
) -> CockpitRead:
    return CockpitRead.model_validate(CockpitService(session).build(period))


@router.post("/candidates/{candidate_id}/profile-suggestion", response_model=ProfileSuggestion)
def suggest_profile(candidate_id: uuid.UUID, session: DatabaseSession) -> ProfileSuggestion:
    return ProfileSuggestion(
        candidate_id=candidate_id,
        text=CockpitService(session).profile_suggestion(candidate_id),
    )


@router.get("/documents", response_model=list[DocumentRead])
def list_documents(
    session: DatabaseSession,
    owner_type: str | None = None,
    owner_id: uuid.UUID | None = None,
) -> list[DocumentRead]:
    documents = DocumentService(session).documents.filtered(
        owner_type=owner_type, owner_id=owner_id
    )
    return [DocumentRead.model_validate(item) for item in documents]


@router.post("/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def create_document(payload: DocumentCreate, session: DatabaseSession) -> DocumentRead:
    return DocumentRead.model_validate(DocumentService(session).create(payload))


@router.post("/documents/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    session: DatabaseSession,
    owner_type: Annotated[str, Form()],
    owner_id: Annotated[uuid.UUID, Form()],
    document_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    uploaded_by: Annotated[str | None, Form()] = None,
) -> DocumentRead:
    _validate_upload_type(file)
    max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
    content = await _read_upload_with_size_limit(file, max_bytes)
    storage_key = save_document_bytes(
        owner_type=owner_type,
        owner_id=owner_id,
        filename=file.filename or "datei",
        content=content,
    )
    payload = DocumentCreate(
        owner_type=owner_type,
        owner_id=owner_id,
        document_type=document_type,
        filename=file.filename or "datei",
        storage_key=storage_key,
        content_type=file.content_type,
        size_bytes=len(content),
        uploaded_by=uploaded_by,
    )
    return DocumentRead.model_validate(DocumentService(session).create(payload))


@router.get("/documents/{document_id}/download")
def download_document(document_id: uuid.UUID, session: DatabaseSession) -> Response:
    # EntityNotFoundError wird global in error_handlers.py auf 404 gemappt.
    document = DocumentService(session).get(document_id)
    try:
        content = read_document_bytes(document.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Datei wurde in der Datenbank gefunden, liegt aber nicht mehr im Speicher.",
        ) from exc
    return Response(
        content=content,
        media_type=document.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{document.filename}"'},
    )


@router.get("/sourcing-metrics", response_model=list[SourcingMetricRead])
def list_sourcing_metrics(session: DatabaseSession) -> list[SourcingMetricRead]:
    return [
        SourcingMetricRead.model_validate(item) for item in SourcingMetricService(session).list()
    ]


@router.post(
    "/sourcing-metrics",
    response_model=SourcingMetricRead,
    status_code=status.HTTP_201_CREATED,
)
def create_sourcing_metric(
    payload: SourcingMetricCreate, session: DatabaseSession
) -> SourcingMetricRead:
    return SourcingMetricRead.model_validate(SourcingMetricService(session).create(payload))


@router.get("/email-templates", response_model=list[EmailTemplateRead])
def list_email_templates(session: DatabaseSession) -> list[EmailTemplateRead]:
    return [
        EmailTemplateRead.model_validate(item) for item in EmailWorkflowService(session).templates()
    ]


@router.post(
    "/email-drafts",
    response_model=EmailDraftRead,
    status_code=status.HTTP_201_CREATED,
)
def create_email_draft(payload: EmailDraftCreate, session: DatabaseSession) -> EmailDraftRead:
    return EmailDraftRead.model_validate(EmailWorkflowService(session).create_draft(payload))
