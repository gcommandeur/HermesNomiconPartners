from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EmailTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Mail-Vorlagen fuer den Mailing-Workflow (Vorlagen-Katalog auf der
    Mailing-Seite) - vorher eine hartcodierte Python-Liste
    (EmailWorkflowService.TEMPLATES), jetzt editierbar in der DB (Auftrag
    "Mailvorlagen editierbar machen"), damit Name/Betreff/Text ohne Deploy
    im CRM angepasst werden koennen.

    `key` bleibt stabil (identisch zu den bisherigen hartcodierten Keys) -
    MailingGroup.template_key referenziert ihn als reinen String (kein FK,
    gleiches Muster wie die anderen "lose" Referenzen in diesem Codebase,
    siehe MailingGroup.recipients), damit eine bestehende Zuordnung nicht
    bricht, auch wenn eine Vorlage spaeter umbenannt/inhaltlich geaendert
    wird. `key` ist deshalb ueber PATCH NICHT aenderbar (siehe
    schemas/operational.py::EmailTemplateUpdate - hat bewusst kein
    key-Feld).

    Platzhalter (z.B. "{candidate}") stehen als literale Tokens in subject/
    body und werden NICHT hier gespeichert - sie werden bei Bedarf per
    Regex aus dem aktuellen subject+body extrahiert (siehe
    EmailWorkflowService.extract_placeholders), damit sie nach einer
    Bearbeitung immer den tatsaechlichen Vorlageninhalt widerspiegeln."""

    __tablename__ = "email_templates"

    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
