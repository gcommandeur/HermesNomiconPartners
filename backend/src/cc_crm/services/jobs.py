from sqlalchemy.orm import Session

from cc_crm.models.job_mandate import JobMandate
from cc_crm.repositories.jobs import JobMandateRepository
from cc_crm.schemas.job_mandate import JobMandateCreate, JobMandateUpdate
from cc_crm.services.base import CrudService
from cc_crm.services.clients import ClientCompanyService


class JobMandateService(CrudService[JobMandate, JobMandateCreate, JobMandateUpdate]):
    def __init__(self, session: Session) -> None:
        repository = JobMandateRepository(session)
        super().__init__(session, repository, "JobMandate")
        self.jobs = repository
        self.clients = ClientCompanyService(session)

    def create(self, payload: JobMandateCreate) -> JobMandate:
        if payload.client_company_id is not None:
            self.clients.get(payload.client_company_id)
        return super().create(payload)
