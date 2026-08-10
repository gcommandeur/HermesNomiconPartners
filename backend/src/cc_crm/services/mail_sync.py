"""IMAP-Abruf, Klassifikation und Zuordnung eingehender Mails.

Ablauf je Postfach: Mails ab last_seen_uid abholen -> als MailMessage
ablegen (Dedup ueber message_id) -> LinkedIn-Mails per Klassifikator
auswerten (siehe mail_classifier.py) -> gegen den Bestand matchen -> bei
eindeutigem Treffer eine Activity anlegen, sonst zum Review vormerken.

Zwei Entwurfsentscheidungen, die den Rest des Moduls erklaeren:

1. Der IMAP-Zugriff steckt hinter der injizierbaren `fetcher`-Funktion mit
   dem schmalen FetchedMail-Datentyp als Grenze. Dadurch ist die gesamte
   Verarbeitungslogik ohne IMAP-Server testbar - genau die Logik (Dedup,
   Selbst-Erkennung, Matching), in der die Fehler stecken.
2. Fehler werden zweistufig behandelt: ein Fehler an EINER Mail wird an
   dieser Mail vermerkt und der Lauf geht weiter (gleiche Robustheit wie
   beim CSV-Import); ein Fehler am KONTO (falsche Zugangsdaten, Netzwerk)
   beendet den Lauf, landet in MailAccount.sync_error und wird der
   Oberflaeche im Klartext gemeldet - sonst ist nicht erkennbar, ob es an
   den Zugangsdaten oder an etwas anderem lag (Nutzer-Vorgabe).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cc_crm.models.activity import Activity
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.contact_person import ContactPerson
from cc_crm.models.enums import MailDirection, MailMatchStatus, TaskPriority, TaskStatus
from cc_crm.models.mail import MailAccount, MailMessage
from cc_crm.models.note import Note
from cc_crm.models.task import Task
from cc_crm.schemas.mail import MailSyncResult
from cc_crm.services.mail_classifier import extract_linkedin_content, is_linkedin_message
from cc_crm.services.mail_credentials import decrypt_password
from cc_crm.services.sourcing import NAME_SIMILARITY_THRESHOLD, normalize_person_name

logger = logging.getLogger("cc_crm.mail_sync")

ACTIVITY_TYPE_LINKEDIN = "linkedin_message"
ACTIVITY_TYPE_EMAIL = "email"

# Obergrenze je manuellem Abruf: ein erstmalig verbundenes Postfach kann
# zehntausende Altmails enthalten - die wuerden den Request sonst
# minutenlang blockieren. Der naechste Abruf macht ab last_seen_uid weiter.
MAX_MESSAGES_PER_RUN = 200

# Terminierungs-Agent (Task + Auto-Kandidat) greift NUR fuer Mails ab diesem
# Datum - Nutzer-Vorgabe: die zuerst eingelesenen 200 historischen Mails
# sollen NICHT rueckwirkend Tasks/Kandidaten erzeugen, nur die bereits
# vorhandenen 18 Activities bleiben unveraendert stehen. Vergleich erfolgt
# gegen MailMessage.received_at (Maildatum), NICHT gegen den Abrufzeitpunkt -
# eine aeltere Mail, die erst spaeter abgerufen wird, loest also weiterhin
# KEINE Automatik aus.
AUTOMATION_CUTOFF = datetime(2026, 8, 9, tzinfo=UTC)

# Ergebnis der Verarbeitung EINER Mail - die Zaehler werden erst nach einem
# erfolgreichen Commit daraus abgeleitet (siehe _process_one).
_Outcome = Literal["activity", "auto_candidate", "pending", "unmatched", "outbound"]


@dataclass(frozen=True)
class FetchedMail:
    """Schmale Grenze zwischen IMAP-Bibliothek und Verarbeitungslogik -
    absichtlich nur die Felder, die wir wirklich auswerten."""

    message_id: str
    uid: str | None
    from_name: str | None
    from_address: str | None
    subject: str | None
    body_text: str | None
    received_at: datetime


@dataclass
class _Counters:
    fetched: int = 0
    created_activities: int = 0
    pending_review: int = 0
    skipped_duplicates: int = 0
    failed_messages: int = 0
    # Separat von created_activities: bei einem Auto-Kandidaten entsteht
    # IMMER auch eine Activity (siehe _process_one), dieser Zaehler macht
    # zusaetzlich sichtbar, dass dabei ohne menschliche Bestaetigung ein
    # neuer Datensatz entstanden ist (Nutzer-Vorgabe).
    auto_created_candidates: int = 0
    highest_uid: str | None = field(default=None)


def _message_id_of(message: object) -> str:
    """RFC-5322 Message-ID aus einer imap-tools-Nachricht als Dedup-Schluessel.

    Nicht jede Mail hat einen Message-ID-Header (selten, aber es kommt vor) -
    dann dient die IMAP-UID als Ersatz, damit ein Abruf nicht an einer
    einzelnen kopflosen Mail scheitert. Die Bibliothek ist untypisiert,
    daher der lokale, eng begrenzte type-ignore statt eines Ignores ueber
    die ganze Funktion.
    """
    headers = message.headers  # type: ignore[attr-defined]
    raw = headers.get("message-id", (None,))
    value = (raw[0] if raw else None) or ""
    return value.strip("<> ") or f"no-message-id-{message.uid}"  # type: ignore[attr-defined]


def fetch_via_imap(account: MailAccount, since_uid: str | None) -> list[FetchedMail]:
    """Echter IMAP-Abruf. Import bewusst lokal, damit die Bibliothek nur
    geladen wird, wenn tatsaechlich abgerufen wird (Tests und alle uebrigen
    Codepfade brauchen sie nicht)."""
    from imap_tools import AND, MailBox, MailBoxUnencrypted

    password = decrypt_password(account.encrypted_password)
    box_cls = MailBox if account.imap_use_ssl else MailBoxUnencrypted

    mails: list[FetchedMail] = []
    with box_cls(account.imap_host, port=account.imap_port).login(
        account.username, password
    ) as mailbox:
        # uid_range holt nur Neues ab dem zuletzt gesehenen Stand; beim
        # allerersten Lauf gibt es keinen Stand -> alles (durch
        # MAX_MESSAGES_PER_RUN begrenzt).
        criteria = AND(uid=f"{int(since_uid) + 1}:*") if since_uid else AND(all=True)
        for message in mailbox.fetch(criteria, limit=MAX_MESSAGES_PER_RUN, bulk=True):
            mails.append(
                FetchedMail(
                    message_id=_message_id_of(message),
                    uid=message.uid,
                    from_name=message.from_values.name if message.from_values else None,
                    from_address=message.from_values.email if message.from_values else None,
                    subject=message.subject,
                    body_text=message.text or message.html,
                    received_at=message.date or datetime.now(UTC),
                )
            )
    return mails


def _safe_error(exc: BaseException, encrypted_password: str) -> str:
    """Fehlertext fuer die Oberflaeche - mit Absicherung, dass niemals das
    Postfach-Passwort darin landet. Manche IMAP-Bibliotheken zitieren den
    fehlgeschlagenen LOGIN-Befehl inklusive Zugangsdaten in der
    Fehlermeldung; das darf nicht in der DB oder im UI erscheinen.

    Nimmt das Chiffrat als String statt des MailAccount-Objekts: die
    Funktion laeuft in Fehlerpfaden, in denen die Session nach einem
    fehlgeschlagenen Flush deaktiviert sein kann - ein Attributzugriff auf
    ein ORM-Objekt wuerde dort einen Lazy-Load ausloesen und mit einem
    Folgefehler scheitern (live im Test aufgetreten).
    """
    text = f"{type(exc).__name__}: {exc}"
    try:
        password = decrypt_password(encrypted_password)
    except Exception:  # noqa: BLE001 - Schluesselproblem darf hier nichts verschlimmern
        return text[:2000]
    if password and password in text:
        text = text.replace(password, "***")
    return text[:2000]


class MailSyncService:
    def __init__(
        self,
        session: Session,
        fetcher: Callable[[MailAccount, str | None], list[FetchedMail]] = fetch_via_imap,
    ) -> None:
        self.session = session
        self._fetch = fetcher
        self._candidate_names: list[tuple[uuid.UUID, str]] | None = None

    # --- oeffentlicher Einstieg ------------------------------------------

    def sync_account(self, account: MailAccount) -> MailSyncResult:
        counters = _Counters()
        # Vorab als einfache Werte sichern: in den Fehlerpfaden unten kann
        # die Session nach einem fehlgeschlagenen Flush deaktiviert sein,
        # dann wuerde jeder ORM-Attributzugriff einen Lazy-Load ausloesen
        # und mit einem Folgefehler scheitern.
        address = account.address
        encrypted_password = account.encrypted_password

        try:
            mails = self._fetch(account, account.last_seen_uid)
        except Exception as exc:  # noqa: BLE001 - jeder Verbindungsfehler ist ein Kontofehler
            logger.warning("IMAP-Abruf fuer %s fehlgeschlagen", address, exc_info=True)
            self.session.rollback()
            error = _safe_error(exc, encrypted_password)
            account.sync_error = error
            self.session.commit()
            return MailSyncResult(mail_account_id=account.id, ok=False, error=error)

        for mail in mails:
            self._process_one(account, mail, counters, address, encrypted_password)

        account.last_synced_at = datetime.now(UTC)
        if counters.highest_uid is not None:
            account.last_seen_uid = counters.highest_uid
        # Erfolgreicher Lauf raeumt eine alte Fehlermeldung weg, damit in der
        # Oberflaeche kein laengst behobener Fehler stehen bleibt.
        account.sync_error = None
        self.session.commit()

        return MailSyncResult(
            mail_account_id=account.id,
            ok=True,
            fetched=counters.fetched,
            created_activities=counters.created_activities,
            pending_review=counters.pending_review,
            skipped_duplicates=counters.skipped_duplicates,
            failed_messages=counters.failed_messages,
            auto_created_candidates=counters.auto_created_candidates,
        )

    # --- Verarbeitung einer einzelnen Mail --------------------------------

    def _process_one(
        self,
        account: MailAccount,
        mail: FetchedMail,
        counters: _Counters,
        address: str,
        encrypted_password: str,
    ) -> None:
        counters.highest_uid = _max_uid(counters.highest_uid, mail.uid)

        if self._already_stored(mail.message_id):
            counters.skipped_duplicates += 1
            return

        account_id = account.id
        try:
            message = self._store_message(account, mail)
            outcome: _Outcome = "outbound"
            if message.direction != MailDirection.OUTBOUND:
                outcome = self._match_and_record(message)
            # Bewusst ein Commit PRO Mail: bei einem Fehler an einer
            # spaeteren Mail muss zurueckgerollt werden, und ein Rollback
            # wuerde sonst auch alle bereits verarbeiteten Mails dieses
            # Laufs verwerfen (live im Test aufgefallen).
            self.session.commit()
        except Exception as exc:  # noqa: BLE001 - eine kaputte Mail darf den Lauf nicht stoppen
            # Rollback ZUERST: nach einem fehlgeschlagenen Flush ist die
            # Session deaktiviert, jeder ORM-Zugriff (auch nur fuers Logging)
            # wuerde sonst mit einem Folgefehler scheitern.
            self.session.rollback()
            logger.warning(
                "Mail %s aus %s konnte nicht verarbeitet werden",
                mail.message_id,
                address,
                exc_info=True,
            )
            counters.failed_messages += 1
            self._store_failed(account_id, mail, _safe_error(exc, encrypted_password))
            return

        # Zaehler erst NACH dem Commit hochsetzen, sonst meldet der Lauf
        # Aktivitaeten, die durch ein fehlgeschlagenes Commit gar nicht
        # entstanden sind.
        counters.fetched += 1
        if outcome in ("activity", "auto_candidate"):
            # Auch bei "auto_candidate" entsteht eine Activity (siehe
            # _match_linkedin) - beide Zaehler werden daher hochgesetzt.
            counters.created_activities += 1
            if outcome == "auto_candidate":
                counters.auto_created_candidates += 1
        elif outcome == "pending":
            counters.pending_review += 1

    def _already_stored(self, message_id: str) -> bool:
        return (
            self.session.scalar(
                select(MailMessage.id).where(MailMessage.message_id == message_id)
            )
            is not None
        )

    def _store_message(self, account: MailAccount, mail: FetchedMail) -> MailMessage:
        is_own = bool(
            mail.from_address
            and mail.from_address.casefold() == account.address.casefold()
        )
        linkedin = is_linkedin_message(
            from_address=mail.from_address,
            from_name=mail.from_name,
            subject=mail.subject,
        )
        message = MailMessage(
            mail_account_id=account.id,
            message_id=mail.message_id,
            imap_uid=mail.uid,
            direction=MailDirection.OUTBOUND if is_own else MailDirection.INBOUND,
            from_name=mail.from_name,
            from_address=mail.from_address,
            subject=mail.subject,
            body_text=mail.body_text,
            received_at=mail.received_at,
            is_linkedin=linkedin,
            match_status=MailMatchStatus.PENDING_REVIEW,
        )
        self.session.add(message)
        self.session.flush()
        return message

    def _store_failed(self, account_id: uuid.UUID, mail: FetchedMail, error: str) -> None:
        """Legt eine minimale Zeile mit Fehlertext an, damit die Mail beim
        naechsten Lauf nicht endlos erneut scheitert und im Review
        nachvollziehbar bleibt. Schlaegt auch das fehl (z.B. weil genau die
        message_id das Problem war), bleibt es beim Log-Eintrag."""
        try:
            self.session.add(
                MailMessage(
                    mail_account_id=account_id,
                    message_id=mail.message_id,
                    imap_uid=mail.uid,
                    direction=MailDirection.INBOUND,
                    from_address=mail.from_address,
                    subject=mail.subject,
                    received_at=mail.received_at,
                    match_status=MailMatchStatus.UNMATCHED,
                    parse_error=error,
                )
            )
            self.session.commit()
        except Exception:  # noqa: BLE001 - auch das Fehler-Protokoll darf nicht stoppen
            logger.exception(
                "Fehlerzeile fuer Mail %s konnte nicht abgelegt werden", mail.message_id
            )
            self.session.rollback()

    # --- Zuordnung --------------------------------------------------------

    def _match_and_record(self, message: MailMessage) -> _Outcome:
        if message.is_linkedin:
            return self._match_linkedin(message)
        return self._match_by_address(message)

    def _match_linkedin(self, message: MailMessage) -> _Outcome:
        content = extract_linkedin_content(
            from_name=message.from_name,
            subject=message.subject,
            body_text=message.body_text,
        )
        # Der bereinigte Antworttext ersetzt den Rohtext als Activity-Inhalt,
        # der Rohtext bleibt in body_text erhalten.
        candidate_id = (
            self._find_candidate_by_name(content.candidate_name)
            if content.candidate_name
            else None
        )

        is_new_candidate = False
        if candidate_id is None:
            if message.received_at >= AUTOMATION_CUTOFF and content.candidate_name:
                # Ab dem Cutoff wird bei fehlendem Fuzzy-Treffer NICHT mehr
                # zum Review vorgemerkt, sondern automatisch ein minimaler
                # Kandidat angelegt (Nutzer-Vorgabe) - anders als beim
                # Sourcing-Lead-Review, wo ein Mensch immer erst bestaetigt.
                # Ohne erkennbaren Personennamen (content.candidate_name is
                # None, z.B. generischer "LinkedIn Recruiter"-Absender) bleibt
                # es beim Review, da es dann nichts anzulegen gaebe.
                candidate_id = self._auto_create_candidate(content.candidate_name, message)
                is_new_candidate = True
            else:
                # Vor dem Cutoff (oder kein Name erkennbar): unveraendertes
                # bisheriges Verhalten - gleiche Governance wie beim
                # Sourcing-Lead-Review, kein automatischer Kandidat.
                message.match_status = MailMatchStatus.PENDING_REVIEW
                return "pending"

        message.matched_candidate_id = candidate_id
        message.match_status = MailMatchStatus.MATCHED
        self._create_activity(
            message,
            activity_type=ACTIVITY_TYPE_LINKEDIN,
            subject=content.role_title or message.subject or "LinkedIn-Nachricht",
            details=content.message_text or message.body_text,
            candidate_id=candidate_id,
        )
        display_name = content.candidate_name or message.from_name or "Unbekannt"
        self._create_followup_task(
            message,
            candidate_id=candidate_id,
            client_company_id=None,
            title=f"LinkedIn-Antwort: {display_name}",
        )
        return "activity" if not is_new_candidate else "auto_candidate"

    def _match_by_address(self, message: MailMessage) -> _Outcome:
        address = (message.from_address or "").strip().casefold()
        if not address:
            message.match_status = MailMatchStatus.UNMATCHED
            return "unmatched"

        candidate_id = self._scalar_id(Candidate, address)
        contact_id = self._scalar_id(ContactPerson, address) if candidate_id is None else None
        company_id = (
            self._scalar_id(ClientCompany, address)
            if candidate_id is None and contact_id is None
            else None
        )

        if candidate_id is None and contact_id is None and company_id is None:
            # Kein Bezug im Bestand (Newsletter, Werbung, Unbekannte):
            # archiviert, aber kein Review noetig.
            message.match_status = MailMatchStatus.UNMATCHED
            return "unmatched"

        message.matched_candidate_id = candidate_id
        message.matched_contact_person_id = contact_id
        message.matched_client_company_id = company_id
        message.match_status = MailMatchStatus.MATCHED

        # Eine Kontaktperson gehoert zu einer Kanzlei - die Activity haengt
        # dann an der Kanzlei, damit sie auf deren Detailseite auftaucht.
        activity_company_id = company_id
        if contact_id is not None:
            contact = self.session.get(ContactPerson, contact_id)
            activity_company_id = contact.client_company_id if contact else None

        self._create_activity(
            message,
            activity_type=ACTIVITY_TYPE_EMAIL,
            subject=message.subject or "E-Mail",
            details=message.body_text,
            candidate_id=candidate_id,
            client_company_id=activity_company_id,
        )
        # Analog zu _match_linkedin: fuer bekannte Absender (Kandidat,
        # Kontaktperson oder Kanzlei) entsteht ab dem Cutoff zusaetzlich ein
        # Nachfass-Task (Nutzer-Vorgabe: "_match_by_address ... bekommt fuer
        # Mails ab Cutoff ebenfalls ein Task spendiert, analog").
        display_name = message.from_name or message.from_address or "Unbekannt"
        self._create_followup_task(
            message,
            candidate_id=candidate_id,
            client_company_id=activity_company_id,
            title=f"E-Mail-Antwort: {display_name}",
        )
        return "activity"

    def _scalar_id(
        self, model: type[Candidate] | type[ContactPerson] | type[ClientCompany], address: str
    ) -> uuid.UUID | None:
        return self.session.scalar(
            select(model.id).where(func.lower(model.email) == address).limit(1)
        )

    def _create_activity(
        self,
        message: MailMessage,
        *,
        activity_type: str,
        subject: str,
        details: str | None,
        candidate_id: uuid.UUID | None = None,
        client_company_id: uuid.UUID | None = None,
    ) -> None:
        activity = Activity(
            candidate_id=candidate_id,
            client_company_id=client_company_id,
            activity_type=activity_type,
            subject=subject[:240],
            details=details,
            occurred_at=message.received_at,
        )
        self.session.add(activity)
        self.session.flush()
        message.created_activity_id = activity.id

    # --- Terminierungs-Agent: Auto-Kandidat + Nachfass-Task ----------------

    def _auto_create_candidate(self, full_name: str, message: MailMessage) -> uuid.UUID:
        """Legt einen minimalen Kandidaten an, wenn eine LinkedIn-Antwort ab
        AUTOMATION_CUTOFF keinem bestehenden Kandidaten per Fuzzy-Match
        zugeordnet werden konnte (Nutzer-Vorgabe: kein Review-Umweg mehr,
        andere Felder werden spaeter ueber den normalen CV-Prozess befuellt).
        Ohne candidate_number - eine Nummernvergabe ausserhalb von Hermes ist
        bewusste Entscheidung, siehe Note unten als Herkunftsnachweis statt
        eines eigenen Schema-Felds (gleiches Muster wie
        SourcingService.approve_lead)."""
        first_name, last_name = _split_name(full_name)
        candidate = Candidate(first_name=first_name, last_name=last_name)
        self.session.add(candidate)
        self.session.flush()
        self.session.add(
            Note(
                candidate_id=candidate.id,
                body=(
                    "Automatisch angelegt aus einer LinkedIn-Antwort ohne "
                    f"Namenstreffer im Bestand (Mail vom {message.received_at:%d.%m.%Y}, "
                    f"Betreff: {message.subject or '-'})."
                ),
            )
        )
        self.session.flush()
        return candidate.id

    def _create_followup_task(
        self,
        message: MailMessage,
        *,
        candidate_id: uuid.UUID | None,
        client_company_id: uuid.UUID | None,
        title: str,
    ) -> None:
        """Nachfass-Task fuer Mails ab AUTOMATION_CUTOFF - vor dem Cutoff
        bleibt es beim bisherigen Verhalten (nur Activity, kein Task)."""
        if message.received_at < AUTOMATION_CUTOFF:
            return
        task = Task(
            candidate_id=candidate_id,
            client_company_id=client_company_id,
            title=title[:240],
            status=TaskStatus.OPEN,
            priority=TaskPriority.NORMAL,
            source_mail_message_id=message.id,
        )
        self.session.add(task)
        self.session.flush()

    # --- Fuzzy-Namensabgleich (wie beim Sourcing-Lead-Review) -------------

    def _find_candidate_by_name(self, full_name: str) -> uuid.UUID | None:
        normalized = _normalize_full_name(full_name)
        if not normalized:
            return None
        best_id: uuid.UUID | None = None
        best_score = 0.0
        for candidate_id, candidate_name in self._all_candidate_names():
            score = _similarity(normalized, candidate_name)
            if score >= NAME_SIMILARITY_THRESHOLD and score > best_score:
                best_id, best_score = candidate_id, score
        return best_id

    def _all_candidate_names(self) -> list[tuple[uuid.UUID, str]]:
        if self._candidate_names is None:
            rows = self.session.execute(
                select(Candidate.id, Candidate.first_name, Candidate.last_name)
            ).all()
            self._candidate_names = [
                (row.id, normalize_person_name(row.first_name or "", row.last_name or ""))
                for row in rows
            ]
        return self._candidate_names


def _split_name(full_name: str) -> tuple[str, str]:
    """Zerlegt einen Anzeigenamen in first_name/last_name - gleiche
    Konvention wie _normalize_full_name: das LETZTE Token ist der Nachname.
    Ein Name ohne Leerzeichen landet komplett in last_name (first_name bleibt
    leer) statt verworfen zu werden - first_name/last_name sind NOT NULL."""
    parts = full_name.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]


def _normalize_full_name(full_name: str) -> str:
    """LinkedIn liefert einen Anzeigenamen am Stueck ("John Paul Fuerus") -
    aufgeteilt wird nur, um dieselbe Normalisierung wie beim Sourcing zu
    nutzen (token-sortiert, dadurch ist die Aufteilung selbst egal)."""
    parts = full_name.split()
    if not parts:
        return ""
    return normalize_person_name(" ".join(parts[:-1]), parts[-1])


def _similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher

    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _max_uid(current: str | None, candidate: str | None) -> str | None:
    """UIDs numerisch vergleichen - ein String-Vergleich wuerde "9" groesser
    als "10" einordnen und den Abrufstand zurueckwerfen."""
    if candidate is None:
        return current
    if current is None:
        return candidate
    try:
        return candidate if int(candidate) > int(current) else current
    except ValueError:
        return current


def sync_all_active(
    session: Session,
    accounts: Iterable[MailAccount] | None = None,
    fetcher: Callable[[MailAccount, str | None], list[FetchedMail]] = fetch_via_imap,
) -> list[MailSyncResult]:
    """Abruf ueber alle aktiven Postfaecher - Einstiegspunkt fuer den
    spaeteren zeitgesteuerten Lauf."""
    service = MailSyncService(session, fetcher=fetcher)
    if accounts is None:
        accounts = session.scalars(
            select(MailAccount).where(MailAccount.is_active.is_(True))
        ).all()
    return [service.sync_account(account) for account in accounts]
