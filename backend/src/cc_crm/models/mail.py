"""Angebundene E-Mail-Postfaecher (IMAP lesend, SMTP schreibend) und die
daraus eingelesenen Nachrichten.

Hintergrund: Hermes soll die zentrale Stelle fuer den gesamten Mailverkehr
werden - eingehende Mails aus den Postfaechern unter
@commandeurconsulting.de werden Kandidat:innen/Kanzlei-Kontakten zugeordnet
und als Activity abgelegt. Prioritaet hat info@, weil dort die
LinkedIn-InMail-Benachrichtigungen mit den Antworten der Kandidat:innen
auflaufen (siehe services/mail_classifier.py).

Passwoerter liegen ausschliesslich Fernet-verschluesselt in
MailAccount.encrypted_password und werden nie im Klartext geloggt oder ueber
die API zurueckgegeben (siehe services/mail_credentials.py).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from cc_crm.models.enums import MailDirection, MailMatchStatus


class MailAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mail_accounts"

    address: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    # Sprechendes Kuerzel fuer die Auswahl in der Oberflaeche, z.B.
    # "info-linkedin", "gege-persoenlich", "contact", "karriere", "lukas".
    label: Mapped[str] = mapped_column(String(80), nullable=False)

    imap_host: Mapped[str] = mapped_column(String(255), nullable=False)
    imap_port: Mapped[int] = mapped_column(Integer, default=993, nullable=False)
    imap_use_ssl: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    smtp_host: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587, nullable=False)
    smtp_use_ssl: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    username: Mapped[str] = mapped_column(String(320), nullable=False)
    # Fernet-Chiffrat, NIE Klartext. Entschluesselung nur unmittelbar vor dem
    # IMAP-/SMTP-Verbindungsaufbau (siehe services/mail_credentials.py).
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Standard-Absender fuer den CV-OUT-Versand an Kanzleien. Bewusst ein
    # umschaltbares DB-Flag statt einer fest verdrahteten Adresse, damit die
    # Versandadresse ohne Deploy aenderbar bleibt (Nutzer-Vorgabe). Der
    # persoenliche Override je Nutzer (User.default_send_account_id) hat
    # Vorrang, siehe dort.
    default_for_cv_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Hoechste bereits verarbeitete IMAP-UID. Bewusst zusaetzlich zu
    # last_synced_at: Serverzeiten weichen ab und Mails koennen nachtraeglich
    # zugestellt werden - ein reiner Zeitstempel-Filter uebersieht die dann.
    last_seen_uid: Mapped[str | None] = mapped_column(String(80))
    # Letzter Fehler beim Abruf (Diagnose in der Einstellungen-Oberflaeche).
    # Ein Fehler deaktiviert das Konto NICHT automatisch - sonst wuerde ein
    # einmaliger Netzwerkaussetzer das Postfach still abschalten.
    sync_error: Mapped[str | None] = mapped_column(Text)


class MailMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Eine eingelesene (oder selbst verschickte) Mail.

    Bewusst ein eigenes Modell statt einer Erweiterung von SourcingLead: bei
    einer LinkedIn-Mail kennen wir nur den Namen, waehrend SourcingLead auf
    Register-Daten (Arbeitgeber/Ort/PLZ/Quell-URL) ausgelegt ist und dessen
    approve_lead() daraus einen Kandidaten baut. Zusaetzlich liefert dieses
    Modell drei Dinge, die der Sync ohnehin braucht: Idempotenz (Dedup ueber
    message_id, ein zweiter Lauf darf keine Dubletten erzeugen), Erhalt der
    Rohdaten (Klassifikator-Fehler spaeter korrigierbar, ohne die Mail neu
    abzuholen) und die Erkennung selbst gesendeter Mails (direction).
    """

    __tablename__ = "mail_messages"

    mail_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # RFC-5322 Message-ID - Dedup-Schluessel ueber alle Laeufe hinweg.
    message_id: Mapped[str] = mapped_column(String(998), nullable=False, unique=True, index=True)
    # IMAP-UID des Kontos, fuer den inkrementellen Abruf (siehe
    # MailAccount.last_seen_uid). Nur innerhalb eines Kontos eindeutig.
    imap_uid: Mapped[str | None] = mapped_column(String(80))

    direction: Mapped[MailDirection] = mapped_column(
        Enum(MailDirection, native_enum=False, length=16),
        default=MailDirection.INBOUND,
        nullable=False,
        index=True,
    )

    from_name: Mapped[str | None] = mapped_column(String(320))
    from_address: Mapped[str | None] = mapped_column(String(320), index=True)
    subject: Mapped[str | None] = mapped_column(String(998))
    body_text: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    is_linkedin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    match_status: Mapped[MailMatchStatus] = mapped_column(
        Enum(MailMatchStatus, native_enum=False, length=24),
        default=MailMatchStatus.PENDING_REVIEW,
        nullable=False,
        index=True,
    )
    matched_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL"), index=True
    )
    matched_contact_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contact_persons.id", ondelete="SET NULL"), index=True
    )
    matched_client_company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("client_companies.id", ondelete="SET NULL"), index=True
    )
    # Rueckverweis auf die erzeugte Activity - verhindert doppelte Activities
    # bei einer erneuten Verarbeitung derselben Mail und macht im Review
    # sichtbar, was aus der Mail geworden ist.
    created_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL")
    )
    # Fehler beim Parsen genau dieser Mail. Eine kaputte Mail darf den
    # Sync-Lauf nicht abbrechen (gleiche Robustheit wie beim CSV-Import) -
    # sie wird mit Fehlertext abgelegt und uebersprungen.
    parse_error: Mapped[str | None] = mapped_column(Text)
