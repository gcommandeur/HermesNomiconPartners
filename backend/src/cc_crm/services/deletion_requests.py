"""Nachverfolgung von Loeschanfragen (Art. 17 DSGVO) - Punkt 3 des Auftrags
"5 Hoch-Punkte umsetzen". Bewusst NUR eine Nachverfolgung UM die bestehende
Anonymisierung (CandidateService.anonymize) herum - die eigentliche
Anonymisierungslogik bleibt unangetastet, "Erledigen" verknuepft lediglich
diesen bereits bestehenden Endpunkt mit completed_at/completed_by_user_id.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from cc_crm.core.errors import ConflictError, EntityNotFoundError
from cc_crm.models.candidate import Candidate
from cc_crm.models.deletion_request import DeletionRequest
from cc_crm.models.user import User
from cc_crm.repositories.deletion_requests import DeletionRequestRepository
from cc_crm.schemas.deletion_request import DeletionRequestRead
from cc_crm.services.candidates import CandidateService

# DSGVO-Standardfrist fuer Auskunfts-/Loeschanfragen (Nutzer-Vorgabe).
DEFAULT_DEADLINE_DAYS = 30


class DeletionRequestService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = DeletionRequestRepository(session)

    def _read(self, request: DeletionRequest, candidate: Candidate) -> DeletionRequestRead:
        return DeletionRequestRead(
            id=request.id,
            candidate_id=request.candidate_id,
            requested_at=request.requested_at,
            requested_via=request.requested_via,
            deadline=request.deadline,
            completed_at=request.completed_at,
            completed_by_user_id=request.completed_by_user_id,
            candidate_first_name=candidate.first_name,
            candidate_last_name=candidate.last_name,
            candidate_number=candidate.candidate_number,
        )

    def _with_candidates(self, requests: Sequence[DeletionRequest]) -> list[DeletionRequestRead]:
        results: list[DeletionRequestRead] = []
        for request in requests:
            candidate = self.session.get(Candidate, request.candidate_id)
            if candidate is None:
                continue
            results.append(self._read(request, candidate))
        return results

    def create(self, candidate_id: uuid.UUID, requested_via: str) -> DeletionRequestRead:
        candidate = self.session.get(Candidate, candidate_id)
        if candidate is None:
            raise EntityNotFoundError(f"Kandidat {candidate_id} nicht gefunden")
        now = datetime.now(UTC)
        request = self.repository.create(
            {
                "candidate_id": candidate_id,
                "requested_at": now,
                "requested_via": requested_via,
                "deadline": now + timedelta(days=DEFAULT_DEADLINE_DAYS),
            }
        )
        self.session.commit()
        return self._read(request, candidate)

    def list_open(self) -> list[DeletionRequestRead]:
        return self._with_candidates(self.repository.list_open())

    def list_all(self) -> list[DeletionRequestRead]:
        return self._with_candidates(self.repository.list_all())

    def complete(self, request_id: uuid.UUID, admin_user: User) -> DeletionRequestRead:
        """Verknuepft die Loeschanfrage mit dem bestehenden Anonymisieren-
        Endpunkt (CandidateService.anonymize, UNVERAENDERT) und markiert die
        Anfrage danach als erledigt."""
        request = self.repository.get(request_id)
        if request is None:
            raise EntityNotFoundError(f"Löschanfrage {request_id} nicht gefunden")
        if request.completed_at is not None:
            raise ConflictError("Löschanfrage wurde bereits erledigt.")

        candidate = CandidateService(self.session).anonymize(request.candidate_id, admin_user)

        request.completed_at = datetime.now(UTC)
        request.completed_by_user_id = admin_user.id
        self.session.commit()
        self.session.refresh(request)
        return self._read(request, candidate)
