"""SMTP-Versand ueber ein bereits verbundenes MailAccount (services/
mail_accounts.py::resolve_send_account waehlt WELCHES) + Ablage der
gesendeten Mail im Sent-Ordner desselben Postfachs per IMAP APPEND, damit sie
auch in Outlook/Webmail auftaucht und die Konversationshistorie nicht
bricht + Activity-Eintrag am Kandidaten/an der Kanzlei/Kontaktperson (gleicher
Mechanismus wie beim eingehenden Mail-Matching, siehe mail_sync.py).

Das war bislang die Hauptluecke: MailAccount hatte bereits smtp_host/-port/
-use_ssl und Fernet-verschluesselte Zugangsdaten, aber keinerlei
Versand-Implementierung.

Gleiches Testbarkeits-Muster wie mail_sync.py: der eigentliche SMTP-/IMAP-
Zugriff steckt hinter injizierbaren Funktionen (`smtp_sender`/
`imap_appender`), damit die gesamte Versandlogik (Tageslimit-Pruefung,
MIME-Aufbau, Activity-Anlage, Attachment-Laden aus dem Storage) OHNE echten
Mailserver testbar ist - das ist zugleich der geforderte Testpfad, der nicht
wirklich versendet.

RATE-LIMITING (zwei unabhaengige, je Postfach konfigurierbare Schutz-
mechanismen, siehe MailAccount.send_throttle_seconds/daily_send_limit):
1. Tageslimit: send_mail() zaehlt die heute bereits ueber dieses Konto
   versendeten Mails (MailMessage mit direction=OUTBOUND) und lehnt einen
   weiteren Versand mit DailyLimitReachedError ab, sobald das Limit
   erreicht ist - der Versand wird dann gar nicht erst versucht.
2. Pause zwischen Sends: NICHT Aufgabe von send_mail() selbst (ein
   Einzelversand darf nicht kuenstlich verzoegert werden) - beim Versenden
   an viele Empfaenger nacheinander (Kanzlei-Streuversand) ist das Aufgabe
   von send_bulk() unten, das zwischen zwei send_mail()-Aufrufen
   send_throttle_seconds pausiert.
"""

from __future__ import annotations

import logging
import smtplib
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, ConsentNotGrantedError
from cc_crm.models.activity import Activity
from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import MailAccountProvider, MailDirection, MailMatchStatus
from cc_crm.models.mail import MailAccount, MailMessage
from cc_crm.models.user import User
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.services.mail_credentials import decrypt_password
from cc_crm.services.storage import read_document_bytes

logger = logging.getLogger("cc_crm.mail_send")

ACTIVITY_TYPE_EMAIL_SENT = "email_sent"
AUDIT_ACTION_CANDIDATE_PROFILE_SENT = "candidate_profile_sent"
AUDIT_ACTION_MAIL_SENT = "mail_sent"

# Gaengige Sent-Ordner-Namen, der Reihe nach probiert (siehe
# _append_to_sent_via_imaplib) - manche Provider (u.a. der aktuell genutzte
# Hoster United Domains) unterstuetzen kein RFC-6154 SPECIAL-USE, dann
# greift dieser Fallback. Ein fehlgeschlagener APPEND ist NICHT fatal fuer
# den Versand selbst (die Mail ist beim Empfaenger bereits angekommen) -
# siehe send_mail().
_COMMON_SENT_FOLDER_NAMES = ("Sent", "INBOX.Sent", "Sent Items", "Gesendet", "INBOX.Gesendet")


class MailSendError(BusinessRuleError):
    """Versand nicht moeglich oder fehlgeschlagen (SMTP-Fehler, deaktiviertes
    Postfach, ...)."""


class DailyLimitReachedError(MailSendError):
    """Eigene Unterklasse, damit send_bulk() diesen einen Fall (Rest des
    Laufs ist ebenfalls aussichtslos) von einem gewoehnlichen Einzelfehler
    (z.B. ungueltige Empfaengeradresse) unterscheiden kann, ohne den
    Fehlertext parsen zu muessen."""


@dataclass(frozen=True)
class MailAttachment:
    """Bereits geladene Anhang-Bytes - siehe MailAttachmentRef fuer den
    ueblichen Fall (Anhang liegt als Document im Storage)."""

    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass(frozen=True)
class MailAttachmentRef:
    """Verweis auf ein bereits im Storage liegendes Dokument (siehe
    services/storage.py::read_document_bytes) - wird von send_mail() ERST
    unmittelbar vor dem jeweiligen Versand geladen, nicht vom Aufrufer im
    Voraus, damit send_bulk() ueber viele Empfaenger nicht dieselbe Datei
    mehrfach gleichzeitig im Speicher haelt."""

    storage_key: str
    filename: str
    content_type: str = "application/octet-stream"


def _build_mime_message(
    *,
    from_address: str,
    from_name: str | None,
    to_address: str,
    to_name: str | None,
    subject: str,
    body_text: str,
    attachments: list[MailAttachment],
) -> MIMEMultipart:
    message = MIMEMultipart()
    message["From"] = formataddr((from_name or "", from_address))
    message["To"] = formataddr((to_name or "", to_address))
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain=from_address.rsplit("@", 1)[-1])
    message.attach(MIMEText(body_text, "plain", "utf-8"))
    for attachment in attachments:
        part = MIMEApplication(attachment.content)
        part.add_header("Content-Disposition", "attachment", filename=attachment.filename)
        part.set_type(attachment.content_type)
        message.attach(part)
    return message


def _send_via_smtplib(
    account: MailAccount, password: str, message: MIMEMultipart, to_address: str
) -> None:
    """Echter SMTP-Versand. Import bewusst lokal, damit smtplib nur bei
    echtem Versand angefasst wird (steht zwar in der stdlib, folgt aber
    demselben Muster wie die lazy Importe fuer imap_tools/boto3 in
    mail_sync.py/storage.py). smtp_use_ssl=True -> implizites TLS (SMTPS,
    typischerweise Port 465), sonst STARTTLS (typischerweise Port 587) -
    gleiche Zwei-Wege-Unterscheidung wie MailAccount.imap_use_ssl fuer IMAP
    (siehe mail_sync.py::fetch_via_imap)."""
    # smtp_host/username sind nur fuer provider=microsoft_graph nullable -
    # dieser Pfad wird ausschliesslich fuer imap_smtp-Konten aufgerufen
    # (siehe send_mail()).
    assert account.smtp_host is not None
    assert account.username is not None
    if account.smtp_use_ssl:
        with smtplib.SMTP_SSL(account.smtp_host, account.smtp_port, timeout=20) as smtp:
            smtp.login(account.username, password)
            smtp.send_message(message, from_addr=account.address, to_addrs=[to_address])
    else:
        with smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(account.username, password)
            smtp.send_message(message, from_addr=account.address, to_addrs=[to_address])


def _append_to_sent_via_imaplib(
    account: MailAccount, password: str, message: MIMEMultipart
) -> bool:
    """Legt die gesendete Mail per IMAP APPEND im Sent-Ordner des Postfachs
    ab. Import bewusst lokal (siehe _send_via_smtplib). Gibt True zurueck,
    sobald IRGENDEIN bekannter Ordnername funktioniert hat, sonst False -
    False ist KEIN Fehler fuer den Aufrufer (siehe send_mail())."""
    import imaplib

    assert account.imap_host is not None
    assert account.username is not None
    raw = message.as_bytes()
    box_cls = imaplib.IMAP4_SSL if account.imap_use_ssl else imaplib.IMAP4
    with box_cls(account.imap_host, account.imap_port) as imap:
        imap.login(account.username, password)
        for folder in _COMMON_SENT_FOLDER_NAMES:
            try:
                status, _ = imap.append(folder, "\\Seen", None, raw)
            except imaplib.IMAP4.error:
                continue
            if status == "OK":
                return True
    return False


def _send_via_graph(
    session: Session,
    *,
    account: MailAccount,
    to_address: str,
    to_name: str | None,
    subject: str,
    body_text: str,
    attachments: list[MailAttachment],
) -> str:
    """Graph-Pfad fuer provider=microsoft_graph - `POST /me/sendMail` legt
    die Mail automatisch in "Gesendete Elemente" ab, das IMAP-APPEND von
    _append_to_sent_via_imaplib entfaellt hier komplett (siehe M365-
    Integrationsplan). Graph gibt bei sendMail keine Message-ID zurueck
    (fire-and-forget, 202 Accepted ohne Body) - fuer den lokalen Dedup-
    Schluessel wird deshalb, wie beim IMAP/SMTP-Pfad, eine eigene erzeugt
    (make_msgid); Kollisionsgefahr mit dem eingehenden Sync besteht nicht,
    da der Mail-Sync ausschliesslich den Posteingang beobachtet (siehe
    mail_sync.py::fetch_via_graph), nicht "Gesendete Elemente"."""
    from cc_crm.integrations.microsoft_graph.client import GraphApiError
    from cc_crm.integrations.microsoft_graph.client import send_mail as graph_send_mail
    from cc_crm.services.graph_token_service import get_valid_access_token

    access_token = get_valid_access_token(session, account)
    try:
        graph_send_mail(
            access_token,
            to_address=to_address,
            to_name=to_name,
            subject=subject,
            body_text=body_text,
            attachments=[(a.filename, a.content_type, a.content) for a in attachments],
        )
    except GraphApiError as exc:
        logger.warning("Graph-Versand ueber %s fehlgeschlagen", account.address, exc_info=True)
        raise MailSendError(f"Versand über {account.address} fehlgeschlagen: {exc}") from exc
    return make_msgid(domain=account.address.rsplit("@", 1)[-1])


def _ensure_consent(session: Session, candidate_id: uuid.UUID | None) -> None:
    """Harter serverseitiger Block (Punkt 1 des Auftrags "5 Hoch-Punkte
    umsetzen"): candidate.consent_received existierte bislang nur als
    Datenfeld, wurde aber nirgends geprueft - jeder Mail-Versand mit
    Kandidatenbezug konnte ein Profil ohne jede Einwilligung verschicken.
    Greift NUR, wenn ueberhaupt ein candidate_id mitgegeben wurde (Mails an
    eine Kanzlei/einen Kontakt ohne Kandidatenbezug sind nicht betroffen).
    Kein Soft-Warning, kein Override - siehe send_bulk() fuer die
    Pro-Empfaenger-Behandlung im Massenversand."""
    if candidate_id is None:
        return
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise ConsentNotGrantedError(
            f"Kandidat {candidate_id} nicht gefunden - Versand abgelehnt."
        )
    if not candidate.consent_received:
        raise ConsentNotGrantedError(
            "Kein Einverständnis des Kandidaten zur Weitergabe erfasst "
            f"(Kandidat: {candidate.first_name} {candidate.last_name})."
        )


def _record_send_audit_log(
    session: Session,
    *,
    current_user: User | None,
    candidate_id: uuid.UUID | None,
    client_company_id: uuid.UUID | None,
    contact_person_id: uuid.UUID | None,
    to_address: str,
    subject: str,
    mail_message_id: uuid.UUID,
) -> None:
    """AuditLog-Eintrag fuer jeden erfolgreichen Mail-Versand (Punkt 2 des
    Auftrags "5 Hoch-Punkte umsetzen": "wer hat wann welches Profil an wen
    geschickt") - gleiches Muster wie services/submissions.py::transition()/
    delete(). entity_type/entity_id zeigen bei Kandidatenbezug auf den
    Kandidaten selbst, damit der Eintrag automatisch in dessen bestehender
    Aenderungshistorie (AuditLogRepository.list_for_candidate) auftaucht."""
    if candidate_id is not None:
        entity_type = "candidate"
        entity_id = candidate_id
        action = AUDIT_ACTION_CANDIDATE_PROFILE_SENT
    else:
        entity_type = "mail_message"
        entity_id = mail_message_id
        action = AUDIT_ACTION_MAIL_SENT
    AuditLogRepository(session).create(
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "changed_by": current_user.email if current_user else None,
            "new_values": {
                "candidate_id": str(candidate_id) if candidate_id else None,
                "client_company_id": str(client_company_id) if client_company_id else None,
                "contact_person_id": str(contact_person_id) if contact_person_id else None,
                "to_address": to_address,
                "subject": subject[:240],
                "mail_message_id": str(mail_message_id),
            },
        }
    )


def _start_of_today_utc() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def sent_today_count(session: Session, account_id: uuid.UUID) -> int:
    """Ueber dieses Konto seit Mitternacht (UTC) versendete Mails - Basis
    fuer die Tageslimit-Pruefung. Zaehlt ueber die ohnehin vorhandene
    MailMessage-Tabelle (direction=OUTBOUND), keine eigene Zaehler-Spalte
    noetig."""
    return int(
        session.scalar(
            select(func.count())
            .select_from(MailMessage)
            .where(
                MailMessage.mail_account_id == account_id,
                MailMessage.direction == MailDirection.OUTBOUND,
                MailMessage.received_at >= _start_of_today_utc(),
            )
        )
        or 0
    )


def send_mail(
    session: Session,
    *,
    account: MailAccount,
    to_address: str,
    subject: str,
    body_text: str,
    to_name: str | None = None,
    attachments: list[MailAttachmentRef] | None = None,
    candidate_id: uuid.UUID | None = None,
    client_company_id: uuid.UUID | None = None,
    contact_person_id: uuid.UUID | None = None,
    current_user: User | None = None,
    smtp_sender: Callable[[MailAccount, str, MIMEMultipart, str], None] = _send_via_smtplib,
    imap_appender: Callable[[MailAccount, str, MIMEMultipart], bool] = _append_to_sent_via_imaplib,
) -> MailMessage:
    """Versendet EINE Mail ueber `account`, legt eine Kopie im Sent-Ordner
    ab und protokolliert Versand (MailMessage) + Aktivitaet (Activity) +
    AuditLog-Eintrag (siehe _record_send_audit_log). Wirft
    DailyLimitReachedError, wenn das Tageslimit des Postfachs bereits
    erreicht ist - der Versand wird dann gar nicht erst versucht. Ein
    fehlgeschlagenes Sent-Ordner-APPEND ist NICHT fatal (best effort) - der
    Versand selbst ist zu diesem Zeitpunkt bereits erfolgreich abgeschlossen.

    Wirft ConsentNotGrantedError, wenn `candidate_id` gesetzt ist und der
    Kandidat keine Einwilligung zur Weitergabe erteilt hat (Punkt 1 des
    Auftrags "5 Hoch-Punkte umsetzen") - diese Pruefung greift VOR dem
    Tageslimit, damit ein abgelehnter Versand nicht unnoetig das Kontingent
    des Postfachs verbraucht.

    `current_user` ist der eingeloggte Nutzer, der den Versand ausgeloest
    hat (Punkt 2 des Auftrags: Audit-Trail) - optional/None fuer
    Aufrufkontexte ohne eingeloggten Nutzer.

    `smtp_sender`/`imap_appender` sind injizierbar (Default: echter
    SMTP-/IMAP-Zugriff) - genau das ist der geforderte Testpfad, der nicht
    wirklich versendet: Tests uebergeben Fake-Funktionen, ohne dass diese
    Funktion selbst irgendein Sonderverhalten fuer Tests braucht."""
    if not account.is_active:
        raise MailSendError(f"Postfach {account.address} ist deaktiviert.")

    _ensure_consent(session, candidate_id)

    already_sent = sent_today_count(session, account.id)
    if already_sent >= account.daily_send_limit:
        raise DailyLimitReachedError(
            f"Tageslimit für {account.address} erreicht ({already_sent}/"
            f"{account.daily_send_limit} bereits heute versendet) - Versand "
            f"morgen fortsetzen oder Limit in den Einstellungen ('E-Mails & "
            f"Konten') anpassen."
        )

    resolved_attachments = [
        MailAttachment(
            filename=ref.filename,
            content=read_document_bytes(ref.storage_key),
            content_type=ref.content_type,
        )
        for ref in (attachments or [])
    ]

    if account.provider == MailAccountProvider.MICROSOFT_GRAPH:
        message_id = _send_via_graph(
            session,
            account=account,
            to_address=to_address,
            to_name=to_name,
            subject=subject,
            body_text=body_text,
            attachments=resolved_attachments,
        )
    else:
        assert account.encrypted_password is not None
        password = decrypt_password(account.encrypted_password)
        mime_message = _build_mime_message(
            from_address=account.address,
            from_name=account.label,
            to_address=to_address,
            to_name=to_name,
            subject=subject,
            body_text=body_text,
            attachments=resolved_attachments,
        )
        try:
            smtp_sender(account, password, mime_message, to_address)
        except Exception as exc:  # noqa: BLE001 - jeder Transportfehler ist ein Versandfehler
            logger.warning("SMTP-Versand ueber %s fehlgeschlagen", account.address, exc_info=True)
            raise MailSendError(f"Versand über {account.address} fehlgeschlagen: {exc}") from exc

        try:
            appended = imap_appender(account, password, mime_message)
            if not appended:
                logger.warning(
                    "Gesendete Mail ueber %s konnte in keinem bekannten Sent-Ordner "
                    "abgelegt werden - der Versand selbst war erfolgreich.",
                    account.address,
                )
        except Exception:  # noqa: BLE001 - Sent-Kopie ist best effort, Versand ist bereits erfolgt
            logger.warning(
                "Ablage im Sent-Ordner von %s fehlgeschlagen (Versand war bereits erfolgreich)",
                account.address,
                exc_info=True,
            )
        message_id = mime_message["Message-ID"]

    now = datetime.now(UTC)
    record = MailMessage(
        mail_account_id=account.id,
        message_id=message_id,
        direction=MailDirection.OUTBOUND,
        from_name=account.label,
        from_address=account.address,
        subject=subject,
        body_text=body_text,
        received_at=now,
        match_status=MailMatchStatus.MATCHED,
        matched_candidate_id=candidate_id,
        matched_client_company_id=client_company_id,
        matched_contact_person_id=contact_person_id,
    )
    session.add(record)
    session.flush()

    activity = Activity(
        candidate_id=candidate_id,
        client_company_id=client_company_id,
        activity_type=ACTIVITY_TYPE_EMAIL_SENT,
        subject=subject[:240],
        details=body_text,
        occurred_at=now,
        sent_by_user_id=current_user.id if current_user else None,
    )
    session.add(activity)
    session.flush()
    record.created_activity_id = activity.id

    _record_send_audit_log(
        session,
        current_user=current_user,
        candidate_id=candidate_id,
        client_company_id=client_company_id,
        contact_person_id=contact_person_id,
        to_address=to_address,
        subject=subject,
        mail_message_id=record.id,
    )

    session.commit()
    session.refresh(record)
    return record


@dataclass(frozen=True)
class BulkRecipient:
    to_address: str
    to_name: str | None = None
    candidate_id: uuid.UUID | None = None
    client_company_id: uuid.UUID | None = None
    contact_person_id: uuid.UUID | None = None


@dataclass
class BulkSendResult:
    sent: list[MailMessage] = field(default_factory=list)
    failed: list[tuple[BulkRecipient, str]] = field(default_factory=list)
    # Ab dem Moment, in dem das Tageslimit mittendrin erreicht wird, sind
    # ALLE restlichen Empfaenger aussichtslos (das Limit sinkt nicht wieder)
    # - sie landen gesammelt hier statt einzeln in `failed`.
    skipped_due_to_daily_limit: list[BulkRecipient] = field(default_factory=list)


def send_bulk(
    session: Session,
    *,
    account: MailAccount,
    recipients: list[BulkRecipient],
    subject: str,
    body_text: str,
    attachments: list[MailAttachmentRef] | None = None,
    current_user: User | None = None,
    sleep: Callable[[float], None] = time.sleep,
    smtp_sender: Callable[[MailAccount, str, MIMEMultipart, str], None] = _send_via_smtplib,
    imap_appender: Callable[[MailAccount, str, MIMEMultipart], bool] = _append_to_sent_via_imaplib,
) -> BulkSendResult:
    """Versendet an mehrere Empfaenger nacheinander, mit
    account.send_throttle_seconds Pause ZWISCHEN zwei Sends (nicht vor dem
    allerersten) - schuetzt vor Provider-Sperren bei einem Kanzlei-
    Streuversand. Ein Fehler bei EINEM Empfaenger (z.B. ungueltige Adresse
    ODER fehlende Einwilligung - siehe ConsentNotGrantedError) bricht den
    restlichen Lauf NICHT ab (gleiche Robustheit wie beim CV-Backfill/
    Mail-Sync): die Consent-Pruefung aus send_mail() greift pro Empfaenger
    einzeln, ein fehlendes Einverstaendnis bei EINEM Kandidaten in der
    Gruppe landet nur fuer diesen in `failed`, alle anderen Empfaenger
    werden trotzdem bedient (Punkt 1 des Auftrags "5 Hoch-Punkte
    umsetzen") - nur das Tageslimit beendet den Lauf vorzeitig, weil ein
    weiterer Versuch dann ohnehin aussichtslos ist."""
    result = BulkSendResult()
    for index, recipient in enumerate(recipients):
        if index > 0:
            sleep(account.send_throttle_seconds)
        try:
            sent_message = send_mail(
                session,
                account=account,
                to_address=recipient.to_address,
                to_name=recipient.to_name,
                subject=subject,
                body_text=body_text,
                attachments=attachments,
                candidate_id=recipient.candidate_id,
                client_company_id=recipient.client_company_id,
                contact_person_id=recipient.contact_person_id,
                current_user=current_user,
                smtp_sender=smtp_sender,
                imap_appender=imap_appender,
            )
            result.sent.append(sent_message)
        except DailyLimitReachedError:
            result.skipped_due_to_daily_limit.append(recipient)
            result.skipped_due_to_daily_limit.extend(recipients[index + 1 :])
            break
        except (MailSendError, ConsentNotGrantedError) as exc:
            result.failed.append((recipient, str(exc)))
    return result
