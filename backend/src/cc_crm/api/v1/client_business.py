# NOMICON: "Geschaeft mit dieser Kanzlei" - nur in der Nomicon-Kopie. Jeder Abschnitt folgt den
# Ansichten und dem Sichtbereich des Nutzers (siehe services/client_business.py).
import uuid
from datetime import date

from fastapi import APIRouter

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.core.errors import EntityNotFoundError
from cc_crm.models.client_company import ClientCompany
from cc_crm.schemas.client_business import ClientBusinessRead
from cc_crm.services.client_business import client_business

router = APIRouter(prefix="/clients")


@router.get("/{client_id}/business", response_model=ClientBusinessRead)
def get_client_business(
    client_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> ClientBusinessRead:
    if session.get(ClientCompany, client_id) is None:
        raise EntityNotFoundError("Kanzlei nicht gefunden")
    return client_business(session, current_user, client_id, date.today())
