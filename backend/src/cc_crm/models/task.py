import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from cc_crm.models.enums import TaskPriority, TaskStatus


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"),
        index=True,
    )
    client_company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("client_companies.id", ondelete="CASCADE"),
        index=True,
    )
    candidate_submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidate_submissions.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, native_enum=False, length=32),
        default=TaskStatus.OPEN,
        nullable=False,
        index=True,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, native_enum=False, length=32),
        default=TaskPriority.NORMAL,
        nullable=False,
        index=True,
    )

    # Zustaendiger Mitarbeiter (Komfort-Filter "Meine Aufgaben", KEINE
    # Sichtbarkeitsgrenze) - siehe models/candidate.py::owner_user_id fuer
    # die vollstaendige Begruendung.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    # "Spaeter erinnern" (POST /tasks/{id}/snooze) - solange dieser Wert in
    # der Zukunft liegt, blendet die offene-Aufgaben-Liste den Task aus,
    # OHNE ihn wie status=DONE endgueltig zu schliessen.
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    # Rueckverweis auf die Mail, aus der dieser Task automatisch entstand
    # (siehe services/mail_sync.py) - nur fuer automatisch erzeugte Tasks
    # gesetzt, bei manuell angelegten None.
    source_mail_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("mail_messages.id", ondelete="SET NULL")
    )
    # Abschlussgrund von POST /tasks/{id}/resolve (siehe schemas/task.py::
    # TaskResolveRequest.outcome) - bisher NUR ephemer verarbeitet (loeste
    # nur status=DONE aus, wurde nirgends gespeichert). Jetzt persistiert,
    # damit z.B. "not_relevant" spaeter auswertbar ist (Nutzer-Vorgabe:
    # "damit man auswerten kann, wie oft der Mail-Agent danebenliegt").
    # Nullable: ueber snooze() geschlossene/noch offene Tasks haben keinen.
    resolution_outcome: Mapped[str | None] = mapped_column(String(40))
