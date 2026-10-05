import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, UUIDPrimaryKeyMixin


class PresentationRecord(UUIDPrimaryKeyMixin, Base):
    """Vorstellungs-Archiv: Nachweis, WAS bei einer Vorstellung an eine Kanzlei gegangen ist
    (Streitfall um das Honorar). Wird beim tatsaechlichen Versand geschrieben
    (services/presentation_archive.py), nie beim blossen Stufenwechsel.

    UNVERAENDERLICH: ein Postgres-Trigger (Migration g3b5d7f9a1c2) lehnt UPDATE und DELETE ab,
    ausgenommen (a) die Aufbewahrungsfrist `retention_until` (+ wer/wann) und (b) das Loeschen
    durch die freigegebene Entfernen-Aktion (transaktionsgebundenes Flag). Bewusst OHNE
    Fremdschluessel auf Kandidat, Kanzlei, Prozess und Nutzer: der Nachweis soll jede spaetere
    Loeschung, Zusammenfuehrung oder Anonymisierung dieser Datensaetze unveraendert ueberleben;
    deshalb stehen Kandidatennummer (Pseudonym) und Kanzleiname als Momentaufnahme hier.

    NUR fuer Admins sichtbar (api/v1/presentation_archive.py). Die Dateien liegen unter dem
    eigenen Speicher-Praefix `presentation-archive/` und NICHT als `documents`-Zeile, damit sie
    in keiner Dokumentenliste, Suche oder Anonymisierung auftauchen."""

    __tablename__ = "presentation_records"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    submission_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True)
    # Pseudonym des Kandidaten ("Nr. XXXX") und Name der Kanzlei zum Versandzeitpunkt.
    candidate_number: Mapped[str | None] = mapped_column(String(40))
    client_name: Mapped[str | None] = mapped_column(String(240))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    sent_by_email: Mapped[str | None] = mapped_column(String(320))
    recipient_emails: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    mail_subject: Mapped[str] = mapped_column(String(998), nullable=False)
    mail_body_text: Mapped[str] = mapped_column(Text, nullable=False)
    mail_message_id: Mapped[str | None] = mapped_column(String(998))
    # Zeile in mail_messages (ohne Fremdschluessel, siehe oben).
    mail_record_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    # Je versendeter Datei: {"storage_key", "filename", "sha256", "size", "content_type"}.
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    profile_text_snapshot: Mapped[str | None] = mapped_column(Text)
    # Vom Admin gesetzt; Voraussetzung fuer jede Entfernung. Die einzige aenderbare Angabe.
    retention_until: Mapped[date | None] = mapped_column(Date)
    retention_set_by: Mapped[str | None] = mapped_column(String(320))
    retention_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PresentationRemovalRequest(UUIDPrimaryKeyMixin, Base):
    """Antrag eines Admins, einen Archiv-Eintrag samt Dateien zu entfernen (Freigabeweg:
    ein ZWEITER Admin entscheidet). Bleibt als Nachweis stehen, enthaelt keine Personendaten
    ausser den Kennungen der beteiligten Admins."""

    __tablename__ = "presentation_removal_requests"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    record_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String(320), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(320))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
