from sqlalchemy.orm import Session

from cc_crm.models.contact_person import ContactPerson
from cc_crm.repositories.contacts import ContactPersonRepository
from cc_crm.schemas.contact_person import ContactPersonCreate, ContactPersonUpdate
from cc_crm.services.base import CrudService
from cc_crm.services.clients import ClientCompanyService


class ContactPersonService(CrudService[ContactPerson, ContactPersonCreate, ContactPersonUpdate]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ContactPersonRepository(session), "ContactPerson")
        self.clients = ClientCompanyService(session)

    def create(self, payload: ContactPersonCreate) -> ContactPerson:
        self.clients.get(payload.client_company_id)
        return super().create(payload)
