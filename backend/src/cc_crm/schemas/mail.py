"""Schemas fuer verbundene Postfaecher.

Sicherheits-Kernregel: das Passwort ist AUSSCHLIESSLICH schreibend. Es gibt
bewusst kein Feld dafuer in MailAccountRead - auch nicht maskiert, auch nicht
verkuerzt. Ein maskierter Wert verleitet dazu, ihn irgendwann doch
durchzureichen; ein gar nicht vorhandenes Feld kann nicht leaken.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from cc_crm.models.enums import MailMatchStatus
from cc_crm.schemas.base import EntityRead


class MailAccountCreate(BaseModel):
    address: EmailStr
    label: str = Field(min_length=1, max_length=80)

    imap_host: str = Field(min_length=1, max_length=255)
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_use_ssl: bool = True

    smtp_host: str = Field(min_length=1, max_length=255)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_use_ssl: bool = True

    username: str = Field(min_length=1, max_length=320)
    # Nur beim Anlegen/Aendern - wird sofort Fernet-verschluesselt abgelegt
    # und nie wieder zurueckgegeben (siehe Modul-Docstring).
    password: str = Field(min_length=1)

    is_active: bool = True
    default_for_cv_out: bool = False


class MailAccountUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    imap_host: str | None = Field(default=None, min_length=1, max_length=255)
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    imap_use_ssl: bool | None = None
    smtp_host: str | None = Field(default=None, min_length=1, max_length=255)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_use_ssl: bool | None = None
    username: str | None = Field(default=None, min_length=1, max_length=320)
    # None = Passwort unveraendert lassen. Ein leerer String waere
    # mehrdeutig ("loeschen" vs. "nicht anfassen") und wird abgelehnt.
    password: str | None = Field(default=None, min_length=1)
    is_active: bool | None = None
    default_for_cv_out: bool | None = None


class MailAccountRead(EntityRead):
    """Bewusst OHNE password/encrypted_password - siehe Modul-Docstring."""

    address: str
    label: str
    imap_host: str
    imap_port: int
    imap_use_ssl: bool
    smtp_host: str
    smtp_port: int
    smtp_use_ssl: bool
    username: str
    is_active: bool
    default_for_cv_out: bool
    last_synced_at: datetime | None
    # Letzter Abruf-Fehler im Klartext, damit in der Oberflaeche erkennbar
    # ist, ob es an den Zugangsdaten oder z.B. am Netzwerk lag
    # (Nutzer-Vorgabe). Enthaelt nie das Passwort - siehe
    # services/mail_sync.py::_safe_error.
    sync_error: str | None


class MailSyncResult(BaseModel):
    """Ergebnis eines manuellen Abrufs ("Jetzt abrufen"-Button).

    Ein fehlgeschlagener Abruf ist KEIN HTTP-Fehler: der Endpunkt liefert
    weiterhin 200 mit ok=False und der Fehlermeldung, damit die Oberflaeche
    den Grund direkt anzeigen kann, statt nur eine generische
    Fehlermeldung zu bekommen.
    """

    mail_account_id: uuid.UUID
    ok: bool
    fetched: int = 0
    created_activities: int = 0
    pending_review: int = 0
    skipped_duplicates: int = 0
    failed_messages: int = 0
    # Automatisch angelegte Kandidat:innen (nur fuer Mails ab
    # services/mail_sync.py::AUTOMATION_CUTOFF ohne Fuzzy-Namenstreffer) -
    # separat ausgewiesen, damit in der Oberflaeche sichtbar ist, dass hier
    # ohne menschliche Bestaetigung ein neuer Datensatz entstanden ist.
    auto_created_candidates: int = 0
    error: str | None = None


class MailMessageRead(BaseModel):
    """Eine Zeile in der Liste der eingelesenen Mails (Postfaecher-Seite).

    Traegt bewusst die aufgeloesten Namen UND IDs der Zuordnung mit, statt
    nur die rohen matched_*_id-Spalten: die Oberflaeche braucht beides fuer
    den direkten Link, ohne dafuer selbst nachzuladen. Eine Kontaktperson hat
    keine eigene Detailseite - matched_contact_person_client_company_id
    traegt deshalb zusaetzlich die Kanzlei-ID, zu der verlinkt werden kann."""

    id: uuid.UUID
    from_name: str | None
    from_address: str | None
    subject: str | None
    received_at: datetime
    match_status: MailMatchStatus
    is_linkedin: bool

    matched_candidate_id: uuid.UUID | None
    matched_candidate_name: str | None

    matched_contact_person_id: uuid.UUID | None
    matched_contact_person_name: str | None
    matched_contact_person_client_company_id: uuid.UUID | None

    matched_client_company_id: uuid.UUID | None
    matched_client_company_name: str | None
