from sqlalchemy.orm import Session

from cc_crm.models.note import Note
from cc_crm.repositories.base import SQLAlchemyRepository


class NoteRepository(SQLAlchemyRepository[Note]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Note)
