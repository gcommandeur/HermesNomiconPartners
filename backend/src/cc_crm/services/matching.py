import re
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, ConflictError, EntityNotFoundError
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import ClientStatus, SubmissionStatus
from cc_crm.models.submission import CandidateSubmission
from cc_crm.repositories.submissions import ACTIVE_SUBMISSION_STATUSES
from cc_crm.schemas.client_company import ClientCompanyRead
from cc_crm.schemas.matching import (
    BulkSubmitRequest,
    BulkSubmitResponse,
    BulkSubmitResultItem,
    ClientMatchRead,
)
from cc_crm.schemas.submission import CandidateSubmissionCreate, CandidateSubmissionTransition
from cc_crm.services.candidates import CandidateService
from cc_crm.services.clients import ClientCompanyService
from cc_crm.services.submissions import CandidateSubmissionService

EXCLUDED_CLIENT_STATUSES = {ClientStatus.BLOCKED, ClientStatus.ARCHIVED}

# Bulk-submit is for getting a qualified candidate's profile out to many
# Kanzleien at once. It intentionally stops at CV_OUT - interviews, offers
# and placements are per-Kanzlei events that cannot happen in bulk.
BULK_SUBMIT_TARGETS = [SubmissionStatus.CV_IN, SubmissionStatus.CV_OUT]

_TOKEN_PATTERN = re.compile(r"[a-zA-ZäöüÄÖÜß]{3,}")


def _tokens(*values: str | None) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        if not value:
            continue
        tokens.update(match.lower() for match in _TOKEN_PATTERN.findall(value))
    return tokens


class CandidateMatchingService:
    """Finds Kanzleien that plausibly fit a candidate and can bulk-create
    CV-Out submissions for a chosen shortlist - the 'candidate -> as many
    relevant Kanzleien as possible, minimal clicks' workflow.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.candidates = CandidateService(session)
        self.clients = ClientCompanyService(session)
        self.submissions = CandidateSubmissionService(session)

    def find_matches(self, candidate_id: uuid.UUID, *, limit: int = 50) -> list[ClientMatchRead]:
        candidate = self.candidates.get(candidate_id)
        candidate_tokens = _tokens(candidate.qualification, candidate.job_title)

        clients: Sequence[ClientCompany] = self.clients.list(offset=0, limit=2000)
        existing_client_ids = self._active_submission_client_ids(candidate_id)

        matches: list[ClientMatchRead] = []
        for client in clients:
            if client.status in EXCLUDED_CLIENT_STATUSES:
                continue
            score, reasons = self._score(candidate_tokens, candidate, client)
            matches.append(
                ClientMatchRead(
                    client=ClientCompanyRead.model_validate(client),
                    score=score,
                    reasons=reasons,
                    already_submitted=client.id in existing_client_ids,
                )
            )

        matches.sort(key=lambda match: (-match.score, match.client.name))
        return matches[:limit]

    def bulk_submit(
        self,
        candidate_id: uuid.UUID,
        payload: BulkSubmitRequest,
        *,
        changed_by: str | None = None,
        owner_user_id: uuid.UUID | None = None,
    ) -> BulkSubmitResponse:
        self.candidates.get(candidate_id)
        if payload.target_status not in BULK_SUBMIT_TARGETS:
            raise BusinessRuleError(
                "Bulk-submit can only target 'cv_in' or 'cv_out' - later stages "
                "(interview, offer, placement) happen per Kanzlei, not in bulk"
            )

        results: list[BulkSubmitResultItem] = []
        created = 0
        skipped = 0
        seen: set[uuid.UUID] = set()
        for client_company_id in payload.client_company_ids:
            if client_company_id in seen:
                continue
            seen.add(client_company_id)
            try:
                submission = self._submit_to_one(
                    candidate_id,
                    client_company_id,
                    payload,
                    changed_by=changed_by,
                    owner_user_id=owner_user_id,
                )
            except (ConflictError, BusinessRuleError, EntityNotFoundError) as exc:
                skipped += 1
                results.append(
                    BulkSubmitResultItem(
                        client_company_id=client_company_id,
                        outcome="skipped",
                        reason=str(exc),
                    )
                )
                continue
            created += 1
            results.append(
                BulkSubmitResultItem(
                    client_company_id=client_company_id,
                    outcome="created",
                    submission_id=submission.id,
                )
            )
        return BulkSubmitResponse(results=results, created_count=created, skipped_count=skipped)

    def _submit_to_one(
        self,
        candidate_id: uuid.UUID,
        client_company_id: uuid.UUID,
        payload: BulkSubmitRequest,
        *,
        changed_by: str | None = None,
        owner_user_id: uuid.UUID | None = None,
    ) -> CandidateSubmission:
        self.clients.get(client_company_id)
        submission = self.submissions.create(
            CandidateSubmissionCreate(
                candidate_id=candidate_id,
                client_company_id=client_company_id,
                owner=payload.owner,
                owner_user_id=owner_user_id,
            ),
            created_by_user_id=owner_user_id,
        )
        for status in self._transition_path(payload.target_status):
            submission = self.submissions.transition(
                submission.id,
                CandidateSubmissionTransition(status=status, changed_by=changed_by),
            )
        return submission

    @staticmethod
    def _transition_path(target: SubmissionStatus) -> list[SubmissionStatus]:
        # Neue Submissions starten direkt bei qualification_call (siehe
        # models/enums.py::SubmissionStatus, models/submission.py-Default) -
        # das ist bereits der Ausgangsstatus, keine Transition dorthin noetig.
        ordered = [
            SubmissionStatus.QUALIFICATION_CALL,
            SubmissionStatus.CV_IN,
            SubmissionStatus.CV_OUT,
        ]
        return ordered[1 : ordered.index(target) + 1]

    def _active_submission_client_ids(self, candidate_id: uuid.UUID) -> set[uuid.UUID]:
        statement = select(CandidateSubmission.client_company_id).where(
            CandidateSubmission.candidate_id == candidate_id,
            CandidateSubmission.status.in_(ACTIVE_SUBMISSION_STATUSES),
            CandidateSubmission.client_company_id.is_not(None),
        )
        return {row for row in self.session.scalars(statement) if row is not None}

    @staticmethod
    def _score(
        candidate_tokens: set[str],
        candidate: Candidate,
        client: ClientCompany,
    ) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []

        focus_tokens = _tokens(client.focus)
        overlap = candidate_tokens & focus_tokens
        if overlap:
            score += 3 * len(overlap)
            reasons.append("Fachgebiet passt zu: " + ", ".join(sorted(overlap)))

        # --- Phase 3: fachliche Schwerpunkte + Kanzleityp (ergänzend, siehe
        # oben stehende Token-Overlap-Logik bleibt unverändert) ---
        schwerpunkte_tokens = _tokens(*(candidate.fachliche_schwerpunkte or []))
        schwerpunkte_overlap = schwerpunkte_tokens & focus_tokens
        if schwerpunkte_overlap:
            score += 3 * len(schwerpunkte_overlap)
            reasons.append(
                "Fachliche Schwerpunkte passen zu: " + ", ".join(sorted(schwerpunkte_overlap))
            )

        # ClientCompany hat aktuell kein eigenes "Kanzleityp"-Feld - genutzt
        # wird stattdessen ein Text-Abgleich von passender_kanzleityp gegen
        # focus + company_size (beide Freitext). Ein dediziertes Kanzleityp-
        # Feld auf ClientCompany würde das zuverlässiger machen.
        client_environment_tokens = focus_tokens | _tokens(client.company_size)
        passender_tokens = _tokens(candidate.passender_kanzleityp)
        if passender_tokens and passender_tokens & client_environment_tokens:
            score += 2
            reasons.append("Passt zum gewünschten Kanzleityp")

        candidate_city = (candidate.city or "").strip().lower()
        client_city = (client.city or "").strip().lower()
        if candidate_city and client_city and candidate_city == client_city:
            score += 2
            reasons.append("Gleiche Stadt")
        elif (
            candidate.postal_code
            and client.postal_code
            and (candidate.postal_code[:1] == client.postal_code[:1])
        ):
            score += 1
            reasons.append("Gleiche PLZ-Region")

        if client.status == ClientStatus.ACTIVE:
            score += 1

        return score, reasons
