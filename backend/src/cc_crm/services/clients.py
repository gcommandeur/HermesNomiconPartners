import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.client_company import ClientCompany
from cc_crm.models.user import User
from cc_crm.repositories.clients import ClientCompanyRepository
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.schemas.client_company import ClientCompanyCreate, ClientCompanyUpdate
from cc_crm.services.base import CrudService
from cc_crm.services.name_matching import (
    SIMILARITY_THRESHOLD,
    name_similarity,
    normalize_company_name,
)


class ClientCompanyService(CrudService[ClientCompany, ClientCompanyCreate, ClientCompanyUpdate]):
    def __init__(self, session: Session) -> None:
        repository = ClientCompanyRepository(session)
        super().__init__(session, repository, "ClientCompany")
        self.clients = repository
        self.audit_logs = AuditLogRepository(session)

    def delete(self, entity_id: uuid.UUID, current_user: User | None = None) -> None:
        # Loeschung ist sicherheits-/nachvollziehbarkeitsrelevant (Punkt 2 des
        # Auftrags) - siehe services/candidates.py::delete fuer dasselbe Muster.
        client = self.get(entity_id)
        self.audit_logs.create(
            {
                "entity_type": "client_company",
                "entity_id": client.id,
                "action": "deleted",
                "changed_by": current_user.email if current_user else None,
                "old_values": {"name": client.name, "kanzleigruppe": client.kanzleigruppe},
            }
        )
        self.session.commit()
        super().delete(entity_id)

    def find_potential_duplicates(
        self,
        *,
        name: str,
        postal_code: str | None = None,
        exclude_id: uuid.UUID | None = None,
    ) -> list[tuple[ClientCompany, float, bool]]:
        """Findet bestehende Kanzleien mit ähnlichem Namen (Marke, nicht
        Rechtsform) - als Warnhilfe vor dem Anlegen einer neuen Kanzlei, damit
        z.B. eine versehentlich doppelt erfasste "Muster Steuerberatung GmbH"
        auffällt, ohne einen echten neuen Standort derselben Marke (andere
        PLZ) zu blockieren. Gibt (Kanzlei, Ähnlichkeit, gleicher_standort)
        sortiert nach Ähnlichkeit absteigend zurück."""
        target = normalize_company_name(name)
        query = select(ClientCompany)
        if exclude_id is not None:
            query = query.where(ClientCompany.id != exclude_id)
        candidates = self.session.scalars(query).all()

        matches: list[tuple[ClientCompany, float, bool]] = []
        for candidate in candidates:
            score = name_similarity(target, normalize_company_name(candidate.name))
            if score < SIMILARITY_THRESHOLD:
                continue
            same_location = bool(
                postal_code
                and candidate.postal_code
                and postal_code.strip() == candidate.postal_code.strip()
            )
            matches.append((candidate, score, same_location))

        matches.sort(key=lambda item: item[1], reverse=True)
        return matches
