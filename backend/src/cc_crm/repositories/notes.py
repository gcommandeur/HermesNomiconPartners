import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.note import Note
from cc_crm.repositories.base import SQLAlchemyRepository


class NoteRepository(SQLAlchemyRepository[Note]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Note)

    def filtered(
        self,
        *,
        candidate_id: uuid.UUID | None = None,
        client_company_id: uuid.UUID | None = None,
        submission_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Note]:
        filters = []
        if candidate_id is not None:
            filters.append(Note.candidate_id == candidate_id)
        if client_company_id is not None:
            filters.append(Note.client_company_id == client_company_id)
        if submission_id is not None:
            filters.append(Note.candidate_submission_id == submission_id)
        elif candidate_id is not None:
            # Ohne explizite submission_id gilt eine Notiz zu einem Kandidaten
            # als "allgemein" (nicht prozessgebunden) - so filtert der neue
            # Notizen-Tab am Kandidaten (kandidaten/[id]/page.tsx) gezielt nur
            # diese, waehrend prozessgebundene Notizen ueber submission_id
            # abgefragt werden.
            filters.append(Note.candidate_submission_id.is_(None))
        statement = (
            select(Note)
            .where(*filters)
            .order_by(Note.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return self.session.scalars(statement).all()
