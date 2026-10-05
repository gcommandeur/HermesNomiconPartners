"""Vorstellungs-Archiv - NUR fuer Admins (Nachweis fuer Honorar-Streitfaelle).

Fuer Nicht-Admins antwortet jede Route mit 404 (nicht 403): das Archiv soll fuer sie nicht
einmal erkennbar sein. Eigene Routen, kein Pfadparameter submission_id/placement_id/fee_id (die
Zugriffsregel fuer Prozesse betrifft das Archiv deshalb nicht - der Zugriff ist ausschliesslich
`ArchiveAdmin`). Siehe services/presentation_archive.py."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.core.errors import EntityNotFoundError
from cc_crm.models.candidate import Candidate
from cc_crm.models.presentation_record import PresentationRecord, PresentationRemovalRequest
from cc_crm.models.user import User
from cc_crm.schemas.presentation_archive import (
    PresentationCountResult,
    PresentationFileRead,
    PresentationRecordDetail,
    PresentationRecordListItem,
    PresentationRecordPage,
    PresentationVerifyItem,
    PresentationVerifyResult,
    RemovalDecision,
    RemovalRequestCreate,
    RemovalRequestRead,
    RetentionUpdate,
)
from cc_crm.services.presentation_archive import (
    PresentationArchiveService,
    count_presented_without_record,
)

router = APIRouter(prefix="/admin/presentation-archive")


def require_archive_admin(current_user: CurrentUser) -> User:
    if not current_user.is_admin:
        raise EntityNotFoundError("Nicht gefunden")
    return current_user


ArchiveAdmin = Annotated[User, Depends(require_archive_admin)]


def _list_item(
    service: PresentationArchiveService, record: PresentationRecord
) -> PresentationRecordListItem:
    candidate = (
        service.session.get(Candidate, record.candidate_id) if record.candidate_id else None
    )
    name = f"{candidate.first_name} {candidate.last_name}".strip() if candidate else None
    return PresentationRecordListItem(
        id=record.id,
        sent_at=record.sent_at,
        client_id=record.client_id,
        client_name=record.client_name,
        candidate_id=record.candidate_id,
        candidate_number=record.candidate_number,
        candidate_name=name,
        submission_id=record.submission_id,
        sent_by_email=record.sent_by_email,
        recipient_emails=list(record.recipient_emails),
        mail_subject=record.mail_subject,
        file_count=len(record.files),
        retention_until=record.retention_until,
        removal_requested=service.pending_request(record.id) is not None,
    )


def _detail(
    service: PresentationArchiveService, record: PresentationRecord
) -> PresentationRecordDetail:
    base = _list_item(service, record)
    return PresentationRecordDetail(
        **base.model_dump(),
        mail_body_text=record.mail_body_text,
        mail_message_id=record.mail_message_id,
        profile_text_snapshot=record.profile_text_snapshot,
        files=[
            PresentationFileRead(
                index=index,
                filename=meta["filename"],
                sha256=meta["sha256"],
                size=int(meta["size"]),
                content_type=meta.get("content_type", "application/octet-stream"),
            )
            for index, meta in enumerate(record.files)
        ],
        retention_set_by=record.retention_set_by,
        retention_set_at=record.retention_set_at,
    )


def _request_read(
    service: PresentationArchiveService, request: PresentationRemovalRequest
) -> RemovalRequestRead:
    record = service.session.get(PresentationRecord, request.record_id)
    return RemovalRequestRead(
        id=request.id,
        record_id=request.record_id,
        reason=request.reason,
        status=request.status,
        requested_by=request.requested_by,
        created_at=request.created_at,
        decided_by=request.decided_by,
        decided_at=request.decided_at,
        decision_note=request.decision_note,
        client_name=record.client_name if record else None,
        candidate_number=record.candidate_number if record else None,
    )


@router.get("", response_model=PresentationRecordPage)
def list_records(
    session: DatabaseSession,
    _admin: ArchiveAdmin,
    client_id: uuid.UUID | None = None,
    candidate_number: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> PresentationRecordPage:
    service = PresentationArchiveService(session)
    rows, total = service.list_records(
        client_id=client_id,
        candidate_number=candidate_number,
        limit=max(1, min(limit, 200)),
        offset=max(0, offset),
    )
    return PresentationRecordPage(total=total, items=[_list_item(service, r) for r in rows])


@router.get("/count-without-record", response_model=PresentationCountResult)
def count_without_record(session: DatabaseSession, _admin: ArchiveAdmin) -> PresentationCountResult:
    """Nur Zaehlung: Prozesse ab cv_out und davon die ohne Archiv-Eintrag (kein Backfill)."""
    presented, missing = count_presented_without_record(session)
    return PresentationCountResult(presented_submissions=presented, without_archive_record=missing)


@router.get("/removal-requests", response_model=list[RemovalRequestRead])
def list_removal_requests(
    session: DatabaseSession, _admin: ArchiveAdmin, status: str | None = None
) -> list[RemovalRequestRead]:
    service = PresentationArchiveService(session)
    return [_request_read(service, r) for r in service.list_requests(status)]


@router.post("/removal-requests/{request_id}/approve", response_model=RemovalRequestRead)
def approve_removal(
    request_id: uuid.UUID,
    payload: RemovalDecision,
    session: DatabaseSession,
    admin: ArchiveAdmin,
) -> RemovalRequestRead:
    service = PresentationArchiveService(session)
    result = service.decide(request_id, admin, approve=True, note=payload.note)
    return _request_read(service, result)


@router.post("/removal-requests/{request_id}/reject", response_model=RemovalRequestRead)
def reject_removal(
    request_id: uuid.UUID,
    payload: RemovalDecision,
    session: DatabaseSession,
    admin: ArchiveAdmin,
) -> RemovalRequestRead:
    service = PresentationArchiveService(session)
    return _request_read(
        service, service.decide(request_id, admin, approve=False, note=payload.note)
    )


@router.get("/{record_id}", response_model=PresentationRecordDetail)
def get_record(
    record_id: uuid.UUID, session: DatabaseSession, _admin: ArchiveAdmin
) -> PresentationRecordDetail:
    service = PresentationArchiveService(session)
    return _detail(service, service.get(record_id))


@router.get("/{record_id}/files/{file_index}")
def download_file(
    record_id: uuid.UUID, file_index: int, session: DatabaseSession, _admin: ArchiveAdmin
) -> Response:
    service = PresentationArchiveService(session)
    meta, content = service.read_file(service.get(record_id), file_index)
    filename = str(meta["filename"]).replace('"', "")
    return Response(
        content=content,
        media_type=meta.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{record_id}/verify", response_model=PresentationVerifyResult)
def verify_record(
    record_id: uuid.UUID, session: DatabaseSession, _admin: ArchiveAdmin
) -> PresentationVerifyResult:
    service = PresentationArchiveService(session)
    items = service.verify(service.get(record_id))
    return PresentationVerifyResult(
        all_ok=all(item["ok"] for item in items),
        files=[PresentationVerifyItem(**item) for item in items],
    )


@router.put("/{record_id}/retention", response_model=PresentationRecordDetail)
def set_retention(
    record_id: uuid.UUID,
    payload: RetentionUpdate,
    session: DatabaseSession,
    admin: ArchiveAdmin,
) -> PresentationRecordDetail:
    service = PresentationArchiveService(session)
    record = service.set_retention(record_id, payload.retention_until, admin)
    return _detail(service, record)


@router.post("/{record_id}/removal-requests", response_model=RemovalRequestRead, status_code=201)
def request_removal(
    record_id: uuid.UUID,
    payload: RemovalRequestCreate,
    session: DatabaseSession,
    admin: ArchiveAdmin,
) -> RemovalRequestRead:
    service = PresentationArchiveService(session)
    return _request_read(service, service.request_removal(record_id, payload.reason, admin))

