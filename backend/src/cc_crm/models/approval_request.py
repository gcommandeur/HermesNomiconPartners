import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ApprovalRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Freigabe-Anfrage eines Nicht-Admins, die ein Admin/GF genehmigt oder
    ablehnt (siehe services/approvals.py). Bis zur Entscheidung bleibt die
    eigentliche Aenderung aus: neue Kanzlei traegt approval_pending, eine
    Honorar-Aenderung lebt nur in proposed_values, eine Rechnung bleibt
    im Entwurf.

    kind: "new_client" | "honorar_change" (entity_type "client_company"),
    "invoice_issue" (entity_type "fee"). status: pending|approved|rejected -
    lose Strings statt DB-Enum, gleiches Muster wie KpiPointRule.stage."""

    __tablename__ = "approval_requests"

    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    requested_by: Mapped[str | None] = mapped_column(String(320))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Bei honorar_change: nur die geaenderten Felder, alt bzw. vorgeschlagen.
    # Bei new_client/invoice_issue: Kerndaten zur Anzeige in der Inbox.
    old_values: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    proposed_values: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    decided_by: Mapped[str | None] = mapped_column(String(320))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
