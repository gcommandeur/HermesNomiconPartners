from sqlalchemy.orm import Session

from cc_crm.models.note import Note
from cc_crm.repositories.notes import NoteRepository
from cc_crm.schemas.note import NoteCreate, NoteUpdate
from cc_crm.services.base import CrudService


class NoteService(CrudService[Note, NoteCreate, NoteUpdate]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, NoteRepository(session), "Note")
