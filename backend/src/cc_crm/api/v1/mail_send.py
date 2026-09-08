"""Einzelversand-Endpoint - reine Anbindung an das bereits bestehende,
getestete services/mail_send.py (Auftrag "Versand-Endpoint nachziehen").

services/mail_send.py existierte bereits vollstaendig (SMTP-Versand,
IMAP-Sent-Ablage, Activity-Log, Anhaenge, Rate-Limiting je Postfach), war
aber ueber keinen Router erreichbar - dieses Modul fuegt NUR die fehlende
Anbindung hinzu, keine neue Versandlogik. Die eigentliche Versandfunktion
(send_mail) wird 1:1 mit ihren eigenen Defaults aufgerufen (kein injizierter
smtp_sender/imap_appender hier) - echte SMTP-/IMAP-Zugriffe sind daher NICHT
Teil der API-Tests dieses Endpoints, dasselbe Muster wie beim bestehenden
POST /mail-accounts/{id}/sync (services/mail_sync.py::fetch_via_imap), der
ebenfalls nur auf Service-Ebene mit einem Fake-fetcher getestet wird. Die
Transportlogik selbst ist bereits umfassend in tests/services/
test_mail_send.py abgedeckt.
"""

from fastapi import APIRouter

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.core.errors import BusinessRuleError
from cc_crm.models.mail import MailAccount
from cc_crm.schemas.mail import MailSendRequest, MailSendResult
from cc_crm.services.mail_accounts import MailAccountService
from cc_crm.services.mail_send import MailAttachmentRef, send_mail
from cc_crm.services.operational import DocumentService

router = APIRouter(prefix="/mail")

# Siehe project_submission_workflow_cv_attachment_guard-Vorgabe: beim
# Mailversand darf serverseitig NIE ein CV-Dokument als Anhang gehen, nur
# das anonyme Profil - hart durchgesetzt, nicht nur im Frontend ausgeblendet.
_FORBIDDEN_ATTACHMENT_DOCUMENT_TYPE = "cv"


@router.post("/send", response_model=MailSendResult)
def send_single_mail(
    payload: MailSendRequest,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> MailSendResult:
    """Versendet eine einzelne Mail mit optionalen Anhaengen ueber ein
    verbundenes Postfach. Kein Kettenauftrag - Profil-Erzeugung und
    Kanzlei-Umkreissuche sind eigenstaendige, separate Schritte."""
    account_service = MailAccountService(session)
    account: MailAccount | None
    if payload.account_id is not None:
        account = account_service.get(payload.account_id)
    else:
        account = account_service.resolve_send_account(current_user)
        if account is None:
            raise BusinessRuleError(
                "Kein Absender-Postfach konfiguriert - bitte in den Einstellungen "
                "('E-Mails & Konten') ein Standardpostfach festlegen oder "
                "account_id im Request angeben."
            )

    document_service = DocumentService(session)
    attachments: list[MailAttachmentRef] = []
    for document_id in payload.attachment_document_ids:
        document = document_service.get(document_id)
        if document.document_type == _FORBIDDEN_ATTACHMENT_DOCUMENT_TYPE:
            raise BusinessRuleError(
                "CV-Dokumente duerfen nicht als Mail-Anhang verschickt werden - "
                "nur das anonyme Profil ('Nr. XXXX.docx')."
            )
        attachments.append(
            MailAttachmentRef(
                storage_key=document.storage_key,
                filename=document.filename,
                content_type=document.content_type or "application/octet-stream",
            )
        )

    record = send_mail(
        session,
        account=account,
        to_address=payload.to_address,
        to_name=payload.to_name,
        subject=payload.subject,
        body_text=payload.body_text,
        attachments=attachments,
        candidate_id=payload.candidate_id,
        client_company_id=payload.client_company_id,
        contact_person_id=payload.contact_person_id,
    )
    return MailSendResult(
        id=record.id,
        mail_account_id=record.mail_account_id,
        to_address=payload.to_address,
        subject=payload.subject,
        sent_at=record.received_at,
        matched_candidate_id=record.matched_candidate_id,
        matched_client_company_id=record.matched_client_company_id,
        matched_contact_person_id=record.matched_contact_person_id,
        created_activity_id=record.created_activity_id,
    )
