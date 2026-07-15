import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status

from cc_crm.api.dependencies import DatabaseSession
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
    content = await file.read()
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
