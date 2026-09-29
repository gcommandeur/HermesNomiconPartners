import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import ClientStatus
from cc_crm.models.user import User
from cc_crm.repositories.clients import ClientCompanyRepository
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.schemas.client_company import ClientCompanyCreate, ClientCompanyUpdate
from cc_crm.services.base import CrudService
from cc_crm.services.geo import (
    candidate_coordinates,
    haversine_km,
    load_postal_locality_index,
    resolve_place_query,
)
from cc_crm.services.name_matching import (
    SIMILARITY_THRESHOLD,
    name_similarity,
    normalize_company_name,
)

# Obergrenze fuer die Kanzlei-Umkreissuche (list_near_candidate) - gleiche
# Ueberlegung wie services/candidates.py::MAX_RADIUS_FILTER_CANDIDATES: die
# Radius-Einschraenkung selbst ist Python-seitig (kein gespeichertes
# lat/lng), daher erst die Basismenge per SQL laden, dann filtern.
MAX_RADIUS_FILTER_CLIENTS = 5000


class ClientCompanyService(CrudService[ClientCompany, ClientCompanyCreate, ClientCompanyUpdate]):
    def __init__(self, session: Session) -> None:
        repository = ClientCompanyRepository(session)
        super().__init__(session, repository, "ClientCompany")
        self.clients = repository
        self.audit_logs = AuditLogRepository(session)

    def list_near_candidate(
        self,
        candidate_id: uuid.UUID,
        *,
        radius_km: int,
        status: ClientStatus | None = None,
    ) -> tuple[list[tuple[ClientCompany, float]], list[ClientCompany]]:
        """Kanzleien im Umkreis eines Kandidaten - Zentrum ist dessen eigene
        PLZ/Ort, NICHT ein freier Suchbegriff (Auftrag "Kanzlei-Umkreissuche
        ausgehend vom Kandidaten"). Eigenstaendig nutzbar, kein Kettenauftrag
        mit Profil-Erzeugung/Mailversand. Wiederverwendet resolve_place_query()
        (fuer das Zentrum, bewusst OHNE den Karten-Jitter - siehe dessen
        Docstring) und haversine_km() aus services/geo.py, keine neue
        Geo-Logik.

        Gibt zwei getrennte Listen zurueck:
        - `in_radius`: (ClientCompany, distance_km)-Paare, nur Kanzleien mit
          aufloesbarer PLZ/Ort UND innerhalb radius_km, nach distance_km
          aufsteigend sortiert.
        - `unresolved`: Kanzleien ohne aufloesbare PLZ/Ort - fallen aus der
          sortierten Liste raus, verschwinden aber NICHT komplett (Nutzer-
          Vorgabe), unabhaengig vom Radius.
        """
        candidate = self.session.get(Candidate, candidate_id)
        if candidate is None:
            raise EntityNotFoundError("Candidate not found")

        center_lat, center_lng, center_precise = resolve_place_query(
            self.session, f"{candidate.postal_code or ''} {candidate.city or ''}".strip()
        )
        if center_lat is None or center_lng is None or not center_precise:
            # Nur ueber den groben PLZ_ZONE_COORDINATES-Fallback aufloesbar
            # zaehlt wie "gar nicht aufloesbar" (kann 100+ km danebenliegen,
            # siehe geo.py::resolve_place_query-Docstring) - sonst wuerde die
            # Umkreissuche ein Zentrum benutzen, das den Kandidaten in
            # Wahrheit falsch verortet.
            raise BusinessRuleError(
                "Kandidat hat keine auflösbare PLZ/Ort - Umkreissuche nicht möglich."
            )

        clients, _ = self.clients.filtered(status=status, limit=MAX_RADIUS_FILTER_CLIENTS)

        # EINMAL fuer die gesamte Umkreissuche geladen statt pro Kanzlei
        # eine eigene DB-Query (N+1-Query-Problem, siehe geo.py::
        # PostalLocalityIndex-Docstring).
        index = load_postal_locality_index(self.session)

        in_radius: list[tuple[ClientCompany, float]] = []
        unresolved: list[ClientCompany] = []
        for client in clients:
            # apply_jitter=False: keine Kartenversatz-Streuung in einer
            # Distanzberechnung fuer einen harten Radius-Filter (siehe
            # geo.py::candidate_coordinates-Docstring).
            lat, lng, precise = candidate_coordinates(
                self.session,
                client.city,
                client.postal_code,
                str(client.id),
                apply_jitter=False,
                index=index,
            )
            if lat is None or lng is None or not precise:
                unresolved.append(client)
                continue
            distance = haversine_km(center_lat, center_lng, lat, lng)
            if distance <= radius_km:
                in_radius.append((client, distance))

        in_radius.sort(key=lambda pair: pair[1])
        return in_radius, unresolved

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
