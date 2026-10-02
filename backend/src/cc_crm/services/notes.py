import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.note import Note
from cc_crm.models.user import User
from cc_crm.repositories.notes import NoteRepository
from cc_crm.schemas.note import NoteCreate, NoteRead, NoteUpdate
from cc_crm.services.base import CrudService


def user_labels(session: Session, user_ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    """Anzeigename (Fallback E-Mail) je Nutzer-ID in EINER Abfrage - fuer
    Autorenangaben an Listen von Notizen/Kommentaren."""
    ids = {user_id for user_id in user_ids if user_id is not None}
    if not ids:
        return {}
    rows = session.execute(
        select(User.id, User.display_name, User.email).where(User.id.in_(ids))
    ).all()
    return {row.id: row.display_name or row.email for row in rows}


def user_labels_by_email(session: Session, emails: Iterable[str | None]) -> dict[str, str]:
    """Wie user_labels, aber ueber die E-Mail (AuditLog.changed_by/
    SubmissionFeedback.created_by speichern die E-Mail als Text)."""
    wanted = {email.lower() for email in emails if email}
    if not wanted:
        return {}
    rows = session.execute(
        select(User.email, User.display_name).where(User.email.in_(wanted))
    ).all()
    return {row.email.lower(): row.display_name or row.email for row in rows}


class NoteService(CrudService[Note, NoteCreate, NoteUpdate]):
    def __init__(self, session: Session) -> None:
        repository = NoteRepository(session)
        super().__init__(session, repository, "Note")
        self.notes = repository

    def create(
        self, payload: NoteCreate, created_by_user_id: uuid.UUID | None = None
    ) -> Note:
        """created_by_user_id kommt immer vom angemeldeten Nutzer (API) bzw.
        dem ausloesenden Nutzer (z.B. Lead-Uebernahme), nie aus dem Payload."""
        note = super().create(payload)
        if created_by_user_id is not None:
            note.created_by_user_id = created_by_user_id
            self.session.commit()
        return note

    def read_many(self, notes: Iterable[Note]) -> list[NoteRead]:
        """NoteRead inkl. aufgeloestem Autorennamen (eine Abfrage fuer alle)."""
        notes = list(notes)
        labels = user_labels(self.session, (note.created_by_user_id for note in notes))
        return [
            NoteRead.model_validate(note).model_copy(
                update={
                    "created_by_name": labels.get(note.created_by_user_id)
                    if note.created_by_user_id
                    else None
                }
            )
            for note in notes
        ]

    def read_one(self, note: Note) -> NoteRead:
        return self.read_many([note])[0]
