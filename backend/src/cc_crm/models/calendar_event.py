import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from cc_crm.models.enums import CalendarEventType


class CalendarEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Allgemeine Kalender-Ebene (Interviews, Quali-Calls, sonstige Termine)
    - eigenstaendig neben der bestehenden `interviews`-Tabelle (dort weiterhin
    an candidate_submissions gebunden, prozessspezifisch). Absichtlich
    generischer: ein Termin gehoert genau einem Nutzer (owner_user_id) und
    kann optional mit Kandidat/Kanzlei/Prozess verknuepft sein, muss es aber
    nicht (z.B. interne Teambesprechung)."""

    __tablename__ = "calendar_events"

    title: Mapped[str] = mapped_column(String(240), nullable=False)
    event_type: Mapped[CalendarEventType] = mapped_column(
        Enum(CalendarEventType, native_enum=False, length=32),
        default=CalendarEventType.OTHER,
        nullable=False,
        index=True,
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # Kein fester Endzeitpunkt fuer alle Termine (z.B. ein kurzer Anruf ohne
    # geplante Dauer) - deshalb optional statt mit einer geratenen Dauer
    # (z.B. +30min) befuellt.
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(240))
    notes: Mapped[str | None] = mapped_column(Text)

    # Wessen Termin das ist (bestimmt Sichtbarkeit) - Pflicht, da ein Termin
    # ohne Owner niemandem zugeordnet und fuer niemanden im Kalender sichtbar
    # waere.
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Wer den Termin angelegt hat - kann vom Owner abweichen, wenn ein Admin
    # einen Termin fuer einen anderen Nutzer eintraegt.
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL")
    )
    client_company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("client_companies.id", ondelete="SET NULL")
    )
    candidate_submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidate_submissions.id", ondelete="SET NULL")
    )

    # Rueckverknuepfung zum Interview, aus dem dieser Termin automatisch
    # erzeugt wurde (siehe services/recruiting.py::create_interview) - anders
    # als candidate_id/client_company_id/candidate_submission_id (SET NULL,
    # bleiben als lose Kontext-Info stehen) hier CASCADE: ein automatisch
    # erzeugter Kalendereintrag ohne sein Quell-Interview waere verwaist und
    # potenziell verwirrend (z.B. nicht mehr nachvollziehbar, warum er
    # existiert). Nullable, da manuell angelegte Termine kein Quell-Interview
    # haben.
    source_interview_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )

    reminder_minutes_before: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    # Microsoft-Graph-Kalender-Sync (Auftrag "M365-Postfach-Integration") -
    # nullable: nur Termine des Nutzers, der ein microsoft_graph-Postfach
    # verbunden hat (MailAccount.oauth_connected_by_user_id), werden
    # gespiegelt (siehe services/calendar_graph_sync.py). external_graph_
    # event_id ist die stabile Graph-Event-ID fuer Update/Delete-Aufrufe;
    # external_graph_last_synced_at ist die Basis der Last-Write-Wins-
    # Konfliktloesung (Vergleich mit Graphs lastModifiedDateTime) - reiner
    # Graph-Zeitstempel, NICHT fuer den Push-Trigger verwenden (siehe unten).
    external_graph_event_id: Mapped[str | None] = mapped_column(String(200), index=True)
    external_graph_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Prod-Vorfall behoben ("Phantom-Push"): updated_at (TimestampMixin,
    # onupdate=func.now()) wird bei JEDER Spaltenaenderung hochgezaehlt -
    # auch wenn ein Pull (Graph->CRM) die Werte geschrieben hat, nicht der
    # Nutzer. Wenn _push_local_changes() dafuer updated_at gegen den
    # GRAPH-Zeitstempel external_graph_last_synced_at vergleicht, sieht
    # JEDE Pull-Aenderung wie eine lokale Aenderung aus - der (gerade erst
    # von Graph korrigierte) Wert wird umgehend wieder zurueckgeschickt.
    # local_last_synced_at ist die eigene, CRM-interne Uhr fuer genau diesen
    # Vergleich: sowohl Push als auch Pull setzen sie per func.now() IN
    # DERSELBEN Schreiboperation wie die Inhaltsfelder, damit sie exakt mit
    # dem resultierenden updated_at uebereinstimmt (kein Read-Back noetig) -
    # erst eine ECHTE, spaetere Aenderung laesst updated_at > local_last_
    # synced_at wieder wahr werden.
    local_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
