import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select

from cc_crm.api.dependencies import CurrentUser, DatabaseSession, process_owner_scope
from cc_crm.core.config import get_settings
from cc_crm.models.candidate import Candidate
from cc_crm.models.operational import Document
from cc_crm.schemas.operational import (
    CockpitRead,
    DocumentCreate,
    DocumentRead,
    EmailDraftCreate,
    EmailDraftRead,
    EmailTemplateRead,
    EmailTemplateUpdate,
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
from cc_crm.services.storage import (
    cv_upload_filename,
    plan_new_candidate_document,
    read_document_bytes,
    rename_document_bytes,
    save_document_bytes,
)

router = APIRouter()

# Whitelist fuer Dokumenten-Uploads (siehe upload_document unten) - orientiert
# an den tatsaechlich im Projekt genutzten Dokumenttypen (CV, Vertrag: PDF/
# Word/gescannte Bilder). Endung UND Content-Type werden geprueft - beides
# kann vom Client gefaelscht werden, aber ohne echtes Content-Sniffing ist das
# ein sinnvoller Kompromiss, der zumindest versehentliche/grob falsche
# Uploads (falscher Dateityp, keine Absicht zu taeuschen) zuverlaessig faengt.
_ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx", ".jpg", ".jpeg", ".png"}
_ALLOWED_UPLOAD_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
}
_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB pro Lese-Schritt


def _validate_upload_type(file: UploadFile) -> str:
    extension = Path(file.filename or "").suffix.lower()
    if extension == ".doc":
        # Altes Word-Binaerformat: es gibt keine saubere Konvertierung, die
        # Bytes lassen sich weder als Text lesen noch per Vision auswerten.
        # Klar ablehnen statt still Muell zu speichern/auszuwerten.
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Das alte Word-Format (.doc) wird nicht unterstuetzt. Bitte die Datei in Word "
                "als .docx oder PDF speichern und erneut hochladen."
            ),
        )
    if extension not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Dateityp nicht erlaubt. Erlaubt sind: PDF, DOCX, JPG, PNG.",
        )
    if file.content_type not in _ALLOWED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Dateityp nicht erlaubt (Content-Type passt nicht zur Dateiendung). "
                "Erlaubt sind: PDF, DOCX, JPG, PNG."
            ),
        )
    return extension


# Magic-Bytes der ersten paar Bytes je erlaubtem Dateityp (Punkt 3 des
# Auftrags "3 Mittel-Punkte umsetzen"): Dateiendung UND vom Client
# mitgeschickter Content-Type (siehe _validate_upload_type oben) sind
# beide frei faelschbar - dieser Check prueft den TATSAECHLICHEN
# Dateiinhalt. DOCX ist technisch ein ZIP-Archiv (OOXML), daher dieselbe
# ZIP-Signatur wie bei jedem .zip - "PK\x03\x04" deckt den ganz
# ueberwiegenden Regelfall (lokaler Datei-Header) ab, "PK\x05\x06"/
# "PK\x07\x08" sind seltene, aber gueltige ZIP-Varianten (leeres/verteiltes
# Archiv). Bewusst KEINE externe Dependency (z.B. python-magic) - die
# erlaubten Typen sind fest und klein genug, dass eine simple Bytes-
# Pruefung ausreicht und keine zusaetzliche System-Abhaengigkeit
# (libmagic) im Docker-Image braucht.
_ALLOWED_UPLOAD_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}


def _validate_upload_signature(extension: str, content: bytes) -> None:
    """Muss NACH dem Einlesen der Datei (siehe _read_upload_with_size_limit)
    und VOR jedem Speichern aufgerufen werden. Ergaenzt die bestehende
    Endungs-/Content-Type-Pruefung (Defense in Depth), ersetzt sie nicht."""
    expected_signatures = _ALLOWED_UPLOAD_SIGNATURES.get(extension)
    if expected_signatures is None:
        return
    if not any(content.startswith(signature) for signature in expected_signatures):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Dateiinhalt passt nicht zur angegebenen Dateiendung "
                f"({extension}) - die Datei scheint beschädigt oder falsch "
                "benannt zu sein."
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
    current_user: CurrentUser,
    # Frontend fragt keinen wählbaren Zeitraum mehr ab (Woche/Monat/Quartal-
    # Umschalter auf der Übersicht wurde entfernt, siehe dashboard-
    # cockpit.tsx) - "month" statt vorher "week", da KPI-Zeiträume sonst zu
    # eng geschnitten waren. Parameter bleibt fuer bestehende/kuenftige
    # direkte API-Aufrufe erhalten.
    period: Annotated[Literal["week", "month", "quarter"], Query()] = "month",
    # Neuer Nutzerfilter oben in der Analytics-Seite (Nutzer-Vorgabe:
    # "standardauswahl sind alle user... Mehrfachauswahl moeglich") -
    # wiederholter Query-Parameter (?owner_user_id=<uuid>&owner_user_id=<uuid>),
    # None (Parameter fehlt) bedeutet "kein Filter" (siehe
    # CockpitService.build-Docstring fuer die None-vs-leere-Liste-Unterscheidung).
    owner_user_id: Annotated[list[uuid.UUID] | None, Query()] = None,
) -> CockpitRead:
    # Ohne expliziten Filter sieht ein Nicht-Admin nur seine eigenen
    # Kandidaten/Prozesse/Aufgaben (Übersicht ruft ohne Parameter auf) - sonst
    # tauchten fremde Eintraege als "wichtig"/"heiss" auf. Admins und
    # explizite Filter (Analytics-Seite) bleiben unveraendert.
    if owner_user_id is None:
        # Mitarbeiter: sich selbst; Teamleiter: sich und sein Team; Admin: None.
        owner_user_id = process_owner_scope(current_user, session)
    return CockpitRead.model_validate(
        CockpitService(session).build(period, owner_user_ids=owner_user_id)
    )


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


def _candidate_upload_naming(
    session: DatabaseSession, owner_id: uuid.UUID, document_type: str, original_filename: str
) -> tuple[str | None, dict[uuid.UUID, str]]:
    """Dateinamens-Konvention fuer neue Kandidaten-Dokumente - zwei Regeln
    je nach document_type (Nutzer-Vorgabe "Schnelle Submission" +
    Dateibenennung):

    - "cv": IMMER "CV_NACHNAME.VORNAME" + Endung (siehe
      services/storage.py::cv_upload_filename), UNABHAENGIG davon, ob die
      candidate_number bereits vergeben ist - die Konvention haengt am
      Namen, nicht an der Nummer.
    - alles andere (Vertraege etc.): bleibt bei der bestehenden Kandidaten-
      Nr.-Konvention ("1823.pdf" statt "ddd4ce82_1823_Kroll_Simon.pdf",
      siehe services/storage.py::plan_new_candidate_document) - dafuer wird
      weiterhin eine gesetzte candidate_number vorausgesetzt, sonst (None,
      {}), und der Aufrufer faellt auf das alte Zufalls-Namensschema
      zurueck.
    """
    candidate = session.get(Candidate, owner_id)
    if candidate is None:
        return None, {}

    existing = list(
        session.scalars(
            select(Document).where(
                Document.owner_type == "candidate", Document.owner_id == owner_id
            )
        ).all()
    )

    if document_type == "cv":
        existing_cv_count = sum(1 for doc in existing if doc.document_type == "cv")
        extension = Path(original_filename).suffix.lower()
        filename = cv_upload_filename(
            first_name=candidate.first_name,
            last_name=candidate.last_name,
            existing_cv_count=existing_cv_count,
            extension=extension,
        )
        # Bewusst keine sibling_renames: die CV-Konvention haengt am Namen,
        # nicht an einer fortlaufenden Nummer - ein bereits vorhandenes CV
        # muss durch den Zaehler eines neuen CVs nicht umbenannt werden.
        return filename, {}

    if not candidate.candidate_number:
        return None, {}
    return plan_new_candidate_document(
        list(existing), candidate.candidate_number, document_type, original_filename
    )


def _apply_sibling_renames(
    session: DatabaseSession, owner_id: uuid.UUID, sibling_renames: dict[uuid.UUID, str]
) -> None:
    """Benennt Geschwister-Dokumente desselben Kandidaten um, falls durch
    den gerade laufenden Upload aus einem bisherigen Einzeldokument ein
    Mehrfachfall wird (siehe _candidate_upload_naming) - selten (nur beim
    Uebergang von 1 auf 2+ Dokumente), aber noetig, um die Konvention
    konsistent zu halten."""
    if not sibling_renames:
        return
    for document_id, new_filename in sibling_renames.items():
        document = session.get(Document, document_id)
        if document is None:
            continue
        new_key = f"{document.owner_type}/{owner_id}/{new_filename}"
        rename_document_bytes(old_storage_key=document.storage_key, new_storage_key=new_key)
        document.storage_key = new_key
        document.filename = new_filename
    session.commit()


@router.post("/documents/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    session: DatabaseSession,
    owner_type: Annotated[str, Form()],
    owner_id: Annotated[uuid.UUID, Form()],
    document_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    uploaded_by: Annotated[str | None, Form()] = None,
) -> DocumentRead:
    extension = _validate_upload_type(file)
    max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
    content = await _read_upload_with_size_limit(file, max_bytes)
    _validate_upload_signature(extension, content)
    original_filename = file.filename or "datei"

    upload_filename = original_filename
    storage_key_override = None
    sibling_renames: dict[uuid.UUID, str] = {}
    if owner_type == "candidate":
        planned_filename, sibling_renames = _candidate_upload_naming(
            session, owner_id, document_type, original_filename
        )
        if planned_filename is not None:
            upload_filename = planned_filename
            storage_key_override = f"{owner_type}/{owner_id}/{planned_filename}"

    storage_key = save_document_bytes(
        owner_type=owner_type,
        owner_id=owner_id,
        filename=original_filename,
        content=content,
        storage_key=storage_key_override,
    )
    payload = DocumentCreate(
        owner_type=owner_type,
        owner_id=owner_id,
        document_type=document_type,
        filename=upload_filename,
        storage_key=storage_key,
        content_type=file.content_type,
        size_bytes=len(content),
        uploaded_by=uploaded_by,
    )
    _apply_sibling_renames(session, owner_id, sibling_renames)
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
    except OSError as exc:
        # Der lokale Dokumentenspeicher liegt im OneDrive-synchronisierten
        # Projektordner - OneDrive "Dateien bei Bedarf" kann selten genutzte
        # Dateien zu reinen Cloud-Platzhaltern machen (ReparsePoint), die bei
        # pausierter/fehlender Synchronisierung nicht lesbar sind. Das ist
        # kein 404 (die Datei existiert, ist nur gerade nicht abrufbar) und
        # kein unbehandelter 500 - klare 503-Meldung statt generischem
        # "Internal Server Error".
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Datei ist gerade nicht verfügbar (vermutlich OneDrive-Synchronisierung). "
                "Bitte in Kürze erneut versuchen."
            ),
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


@router.patch("/email-templates/{key}", response_model=EmailTemplateRead)
def update_email_template(
    key: str, payload: EmailTemplateUpdate, session: DatabaseSession
) -> EmailTemplateRead:
    # EntityNotFoundError wird global in error_handlers.py auf 404 gemappt.
    service = EmailWorkflowService(session)
    template = service.update_template(key, payload)
    return EmailTemplateRead.model_validate(
        {
            "key": template.key,
            "name": template.name,
            "subject": template.subject,
            "body": template.body,
            "placeholders": service.extract_placeholders(template.subject, template.body),
        }
    )


@router.post(
    "/email-drafts",
    response_model=EmailDraftRead,
    status_code=status.HTTP_201_CREATED,
)
def create_email_draft(payload: EmailDraftCreate, session: DatabaseSession) -> EmailDraftRead:
    return EmailDraftRead.model_validate(EmailWorkflowService(session).create_draft(payload))
