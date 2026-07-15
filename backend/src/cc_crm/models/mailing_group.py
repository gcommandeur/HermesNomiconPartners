from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MailingGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Benannte, gespeicherte Menge von Mailing-Empfaengern (Kandidaten/
    Kanzleien/Kontakte, je nach `kind`). Grundlage fuer Punkt 6 (Auswahl aus
    Geo-Mapping / "Fuer Mailing nutzen") und Punkt 7 (Mailing-Seite: Gruppen
    lesen, zusammenfuehren, Vorlage zuordnen).

    `recipients` ist bewusst ein JSON-Feld (wie z.B. Candidate.no_gos,
    JobMandate.must_have in diesem Codebase) statt einer separaten
    Join-Tabelle - die Empfaenger sind heterogen (drei verschiedene
    Quelltabellen) und werden nie einzeln abgefragt, nur als komplette Liste
    pro Gruppe gelesen/geschrieben.
    """

    __tablename__ = "mailing_groups"

    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    # Liste von {"kind": "candidate"|"client"|"contact", "id": str, "name": str, "email": str|None}
    recipients: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    # Vorlagen-Zuordnung (Punkt 7) - referenziert EmailTemplate.key aus dem
    # bestehenden EmailWorkflowService.TEMPLATES, kein eigenes Vorlagenmodell.
    template_key: Mapped[str | None] = mapped_column(String(80))
