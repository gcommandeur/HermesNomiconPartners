from collections.abc import Sequence

from sqlalchemy.orm import Session

from cc_crm.models.contact_person import ContactPerson
from cc_crm.repositories.contacts import ContactPersonRepository
from cc_crm.schemas.contact_person import ContactPersonCreate, ContactPersonUpdate
from cc_crm.services.base import CrudService
from cc_crm.services.clients import ClientCompanyService


class ContactPersonService(CrudService[ContactPerson, ContactPersonCreate, ContactPersonUpdate]):
    custom_field_entity = "contact"

    def __init__(self, session: Session) -> None:
        repository = ContactPersonRepository(session)
        super().__init__(session, repository, "ContactPerson")
        self.contacts = repository
        self.clients = ClientCompanyService(session)

    def create(self, payload: ContactPersonCreate) -> ContactPerson:
        self.clients.get(payload.client_company_id)
        return super().create(payload)

    def list_filtered(
        self,
        *,
        search: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[ContactPerson], int]:
        entities, total = self.contacts.filtered(search=search, offset=offset, limit=limit)
        self._attach_client_company_names(entities)
        return entities, total

    def _attach_client_company_names(self, contacts: Sequence[ContactPerson]) -> None:
        client_ids = [contact.client_company_id for contact in contacts]
        names = self.contacts.client_company_names(client_ids)
        for contact in contacts:
            contact.client_company_name = names.get(contact.client_company_id)  # type: ignore[attr-defined]
