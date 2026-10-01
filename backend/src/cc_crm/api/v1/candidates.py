import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, File, Query, Response, UploadFile, status

from cc_crm.api.dependencies import AdminUser, CurrentUser, DatabaseSession
from cc_crm.api.v1.operational import (
    _read_upload_with_size_limit,
    _validate_upload_signature,
    _validate_upload_type,
)
from cc_crm.core.config import get_settings
from cc_crm.models.enums import Abschlussart, CandidateStatus, CvExtractionJobStatus, Rolle
from cc_crm.repositories.candidates import compute_search_match_fields
from cc_crm.schemas.candidate import (
    CandidateCreate,
    CandidateRead,
    CandidateUpdate,
    CvExtractionRequest,
    CvExtractionSuggestion,
    CvPreviewResponse,
)
from cc_crm.schemas.cv_out import CvOutContact, CvOutTargetClient, CvOutTargetsResult
from cc_crm.schemas.pagination import Page
from cc_crm.schemas.recruiting import AuditLogRead
from cc_crm.schemas.submission import (
    CandidatePitchLogCreate,
    CandidatePitchLogRead,
    CandidateQuickLogCreate,
    CandidateQuickLogResult,
    CandidateStageSummary,
    CandidateSubmissionRead,
)
from cc_crm.services.candidates import CandidateService
from cc_crm.services.cv_extraction import (
    CV_STRUCTURED_FIELDS,
    CvSourceKind,
    classify_cv_source,
    extract_candidate_fields,
    extract_text_from_bytes,
    is_agency_letterhead,
)
from cc_crm.services.cv_extraction_jobs import (
    create_job,
    get_job_for_user,
    run_scan_job_in_background,
)
from cc_crm.services.operational import DocumentService
from cc_crm.services.recruiting import RecruitingProcessService
from cc_crm.services.storage import read_document_bytes
from cc_crm.services.submissions import CandidateSubmissionService

router = APIRouter(prefix="/candidates")


@router.get("", response_model=Page[CandidateRead])
def list_candidates(
    session: DatabaseSession,
    candidate_status: Annotated[CandidateStatus | None, Query(alias="status")] = None,
    role: str | None = None,
    # Mehrfach angebbar (?rollen=steuerberater&rollen=partner) - ODER-
    # verknuepft, siehe repositories/candidates.py::filtered. Anders als
    # `role` (Freitext-Filter auf job_title) filtert dies auf die
    # normalisierte Candidate.rollen-Taxonomie (models/enums.py::Rolle) -
    # beide Filter sind unabhaengig nutzbar, auch zusammen mit `search`.
    rollen: Annotated[list[Rolle] | None, Query()] = None,
    # Gleiches Muster wie rollen oben (Mehrfachauswahl, ODER-verknuepft) -
    # filtert auf die strukturierte Abschlussart-Taxonomie (models/enums.py::
    # Abschlussart), unabhaengig von rollen nutzbar.
    abschluesse: Annotated[list[Abschlussart] | None, Query()] = None,
    region: str | None = None,
    search: str | None = None,
    # Echter PLZ+Umkreis-Filter (siehe services/candidates.py::
    # _list_filtered_by_radius) - unabhaengig vom bestehenden `region`
    # (reiner Substring-Match) und kombinierbar mit search/rollen. Beide
    # Parameter muessen gesetzt sein, sonst greift kein Umkreis-Filter.
    plz_ort: str | None = None,
    radius_km: Annotated[int | None, Query(ge=1, le=500)] = None,
    owner_user_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    # Titelschutz-Korrektur Schritt 2: eigener Filter fuer Kandidaten mit
    # unbestaetigter geschuetzter Rolle (siehe models/candidate.py::
    # rollen_unbestaetigt) - sonst findet man sie im laufenden Betrieb nicht
    # wieder. True/False filtert, None (Default) laesst den Filter aus.
    rollen_unbestaetigt: bool | None = None,
    sort_by: Annotated[
        Literal["candidate_number", "name", "job_title", "city", "salary_expectation", "status"]
        | None,
        Query(),
    ] = None,
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "asc",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Page[CandidateRead]:
    # owner_user_id ist ein reiner Komfort-Filter ("Meine Kandidaten") - ohne
    # ihn sehen weiterhin alle Nutzer alle Kandidaten, keine Sichtbarkeitsgrenze.
    entities, total = CandidateService(session).list_filtered(
        status=candidate_status,
        role=role,
        rollen=rollen,
        abschluesse=abschluesse,
        region=region,
        plz_ort=plz_ort,
        radius_km=radius_km,
        search=search,
        owner_user_id=owner_user_id,
        created_from=created_from,
        created_to=created_to,
        rollen_unbestaetigt=rollen_unbestaetigt,
        sort_by=sort_by,
        sort_dir=sort_dir,
        offset=offset,
        limit=limit,
    )
    # Nachvollziehbarkeit fuer die erweiterte Freitextsuche (Punkt 5) - NUR
    # fuer die aktuell zurueckgegebene Seite berechnet, nicht fuer den
    # gesamten (potenziell grossen) Treffer-Bestand. Kein Effekt, wenn
    # search leer/nicht gesetzt ist (compute_search_match_fields liefert
    # dann ([], [])).
    items = []
    for candidate in entities:
        read = CandidateRead.model_validate(candidate)
        if search:
            matched_fields, matched_values = compute_search_match_fields(candidate, search)
            read = read.model_copy(
                update={
                    "search_match_fields": matched_fields,
                    "search_matched_values": matched_values,
                }
            )
        items.append(read)
    return Page(items=items, total_count=total, limit=limit, offset=offset)


@router.post("", response_model=CandidateRead, status_code=status.HTTP_201_CREATED)
def create_candidate(
    payload: CandidateCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> CandidateRead:
    if payload.owner_user_id is None:
        payload = payload.model_copy(update={"owner_user_id": current_user.id})
    return CandidateRead.model_validate(CandidateService(session).create(payload))


@router.post("/cv-preview", response_model=CvPreviewResponse)
async def preview_cv_fields(
    file: Annotated[UploadFile, File()],
    background_tasks: BackgroundTasks,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> CvPreviewResponse:
    """Liest ein CV aus, BEVOR der Kandidat angelegt ist (Anlegen-Formular,
    Nutzer-Feedback: "Felder sollen ausgefuellt werden") - anders als
    /{candidate_id}/cv-extraction gibt es hier noch keinen Kandidaten,
    gegen den "bereits befuellte Felder" geprueft werden koennten, daher
    werden alle erkannten Felder zurueckgegeben (das Frontend uebernimmt sie
    nur in aktuell leere Formularfelder, ueberschreibt also ebenfalls nichts
    manuell Eingegebenes).

    Gescannte PDFs (kein brauchbarer Text-Layer) brauchen eine mehrseitige
    Vision-Auswertung, die das Gateway-Timeout sprengen wuerde: hier kommt
    sofort status="processing" plus job_id zurueck, das Ergebnis liefert
    GET /candidates/cv-preview/{job_id}. Alles andere (Text-PDF, DOCX, ein
    einzelnes Bild) wird wie bisher inline ausgewertet."""
    extension = _validate_upload_type(file)
    max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
    content = await _read_upload_with_size_limit(file, max_bytes)
    _validate_upload_signature(extension, content)
    filename = file.filename or "cv.pdf"
    cv_text = extract_text_from_bytes(filename, content)
    kind = classify_cv_source(filename, content, cv_text)
    if kind is CvSourceKind.SCANNED_PDF:
        job = create_job(session, current_user.id)
        background_tasks.add_task(run_scan_job_in_background, job.id, filename, content)
        return CvPreviewResponse(status="processing", job_id=job.id)
    extracted = extract_candidate_fields(
        cv_text, filename=filename, content=content, source_kind=kind
    )
    # CV_STRUCTURED_FIELDS statt Feld-fuer-Feld-Aufzaehlung - siehe Kommentar
    # dort zur zentralen Registry.
    values = {field: extracted.get(field) or None for field in CV_STRUCTURED_FIELDS}
    return CvPreviewResponse.model_validate(
        {**values, "source_is_agency_profile": is_agency_letterhead(cv_text)}
    )


@router.get("/cv-preview/{job_id}", response_model=CvPreviewResponse)
def get_cv_preview_result(
    job_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> CvPreviewResponse:
    job = get_job_for_user(session, job_id, current_user)
    if job.status is CvExtractionJobStatus.PROCESSING:
        return CvPreviewResponse(status="processing", job_id=job.id)
    if job.status is CvExtractionJobStatus.FAILED:
        return CvPreviewResponse(status="failed", job_id=job.id, error=job.error)
    return CvPreviewResponse.model_validate(
        {**(job.result or {}), "status": "done", "job_id": job.id}
    )


# Muss vor /{candidate_id} registriert sein, sonst faengt die Path-Param-Route
# "reactivation-list" als ungueltige candidate_id ab.
@router.get("/reactivation-list", response_model=list[CandidateRead])
def list_reactivation_candidates(
    session: DatabaseSession,
    threshold_months: Annotated[int | None, Query(ge=1)] = None,
) -> list[CandidateRead]:
    candidates = CandidateService(session).reactivation_candidates(threshold_months)
    return [CandidateRead.model_validate(candidate) for candidate in candidates]


@router.get("/{candidate_id}", response_model=CandidateRead)
def get_candidate(candidate_id: uuid.UUID, session: DatabaseSession) -> CandidateRead:
    return CandidateRead.model_validate(CandidateService(session).get(candidate_id))


@router.patch("/{candidate_id}", response_model=CandidateRead)
def update_candidate(
    candidate_id: uuid.UUID,
    payload: CandidateUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> CandidateRead:
    return CandidateRead.model_validate(
        CandidateService(session).update(candidate_id, payload, current_user)
    )


@router.post("/{candidate_id}/confirm-rollen", response_model=CandidateRead)
def confirm_candidate_rollen(
    candidate_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> CandidateRead:
    """"Bestätigen"-Aktion (Titelschutz-Korrektur Schritt 2): der Nutzer hat
    die Rolle geprueft (z.B. im Original-CV nachgesehen) und bestaetigt sie
    als korrekt - loescht nur Candidate.rollen_unbestaetigt, rollen selbst
    bleibt unangetastet. Fuer die Gegenaktion ("Rolle korrigieren") gibt es
    bewusst keinen eigenen Endpoint - das ist einfach das normale PATCH
    oben (siehe CandidateService.update())."""
    return CandidateRead.model_validate(
        CandidateService(session).confirm_rollen(candidate_id, current_user)
    )


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(
    candidate_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> Response:
    CandidateService(session).delete(candidate_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{candidate_id}/history", response_model=list[AuditLogRead])
def get_candidate_history(candidate_id: uuid.UUID, session: DatabaseSession) -> list[AuditLogRead]:
    """Änderungshistorie fürs Kandidatenprofil (Timeline-Tab) - was/wann/
    durch wen, siehe services/candidates.py::CandidateService.history.
    Bewusst NICHT admin-only wie GET /audit-logs (das globale Log): die
    eigene Kandidaten-Historie ist regulärer Bestandteil des Profils."""
    entries = CandidateService(session).history(candidate_id)
    return [AuditLogRead.model_validate(entry) for entry in entries]


@router.get("/{candidate_id}/cv-out-targets", response_model=CvOutTargetsResult)
def get_candidate_cv_out_targets(
    candidate_id: uuid.UUID,
    session: DatabaseSession,
    # Gleiche Stufen/Grenzen wie der bestehende Kanzlei-Umkreisfilter (siehe
    # api/v1/clients.py::list_clients_near_candidate).
    radius_km: Annotated[int, Query(ge=1, le=500)],
) -> CvOutTargetsResult:
    """CV-Out-Kampagne: Kanzleien im Umkreis des Kandidaten mit
    mailingfaehigen Kontakten (nicht gesperrt, mind. ein Kontakt mit
    E-Mail) - siehe CandidateService.cv_out_targets fuer Consent-Check und
    Filterlogik. Legt noch keine MailingGroup an, das passiert erst nach
    Bestaetigung der Auswahl im Frontend."""
    targets = CandidateService(session).cv_out_targets(candidate_id, radius_km=radius_km)
    return CvOutTargetsResult(
        candidate_id=str(candidate_id),
        radius_km=radius_km,
        targets=[
            CvOutTargetClient(
                id=str(client.id),
                name=client.name,
                location=", ".join(part for part in [client.postal_code, client.city] if part)
                or "Ort unbekannt",
                postal_code=client.postal_code,
                status=client.status.value,
                distance_km=round(distance, 1),
                contacts=[
                    CvOutContact(
                        id=str(contact.id),
                        first_name=contact.first_name,
                        last_name=contact.last_name,
                        email=contact.email or "",
                        role_title=contact.role_title,
                        is_primary=contact.is_primary,
                    )
                    for contact in contacts
                ],
            )
            for client, distance, contacts in targets
        ],
    )


@router.post("/{candidate_id}/anonymize", response_model=CandidateRead)
def anonymize_candidate(
    candidate_id: uuid.UUID, session: DatabaseSession, admin: AdminUser
) -> CandidateRead:
    """Admin-only, technische DSGVO-Vorbereitung (Punkt 4 des Auftrags,
    keine Rechtsberatung) - siehe CandidateService.anonymize."""
    return CandidateRead.model_validate(CandidateService(session).anonymize(candidate_id, admin))


@router.get("/{candidate_id}/submissions", response_model=list[CandidateSubmissionRead])
def list_candidate_submissions(
    candidate_id: uuid.UUID,
    session: DatabaseSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[CandidateSubmissionRead]:
    return [
        CandidateSubmissionRead.model_validate(submission)
        for submission in CandidateSubmissionService(session).list_for_candidate(
            candidate_id, offset=offset, limit=limit
        )
    ]


@router.post("/{candidate_id}/quick-log", response_model=CandidateQuickLogResult)
def quick_log_candidate_stage(
    candidate_id: uuid.UUID,
    payload: CandidateQuickLogCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> CandidateQuickLogResult:
    """Quali-Call-Notiz anlegen - startet dabei bei Bedarf automatisch
    einen Prozess (siehe RecruitingProcessService.quick_log), ohne dass vorher
    eine separate "Prozess erstellen"-Aktion noetig ist."""
    return RecruitingProcessService(session).quick_log(
        candidate_id,
        payload,
        changed_by=current_user.email,
        owner_user_id=current_user.id,
    )


@router.post("/{candidate_id}/pitch-log", response_model=CandidatePitchLogRead)
def log_candidate_pitch(
    candidate_id: uuid.UUID,
    payload: CandidatePitchLogCreate,
    session: DatabaseSession,
) -> CandidatePitchLogRead:
    """Loggt ein Pitch/InMail-Ereignis - bewusst OHNE Prozess-Anlage/
    Statuswechsel (anders als quick-log oben), siehe
    RecruitingProcessService.log_pitch/CandidatePitchLog-Docstring."""
    return CandidatePitchLogRead.model_validate(
        RecruitingProcessService(session).log_pitch(candidate_id, payload)
    )


@router.get("/{candidate_id}/stage-summary", response_model=CandidateStageSummary)
def get_candidate_stage_summary(
    candidate_id: uuid.UUID, session: DatabaseSession
) -> CandidateStageSummary:
    return RecruitingProcessService(session).stage_summary(candidate_id)


@router.post("/{candidate_id}/cv-extraction", response_model=CvExtractionSuggestion)
def extract_cv_fields(
    candidate_id: uuid.UUID,
    payload: CvExtractionRequest,
    session: DatabaseSession,
) -> CvExtractionSuggestion:
    document = DocumentService(session).get(uuid.UUID(payload.document_id))
    content = read_document_bytes(document.storage_key)
    cv_text = extract_text_from_bytes(document.filename, content)
    return CandidateService(session).auto_fill_from_cv(
        candidate_id, cv_text, filename=document.filename, content=content
    )
