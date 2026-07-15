import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.config import get_settings
from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import CandidateStatus
from cc_crm.repositories.candidates import CandidateRepository
from cc_crm.schemas.candidate import CandidateCreate, CandidateUpdate, CvExtractionSuggestion
from cc_crm.services.base import CrudService
from cc_crm.services.cv_extraction import extract_candidate_fields, is_agency_letterhead

# Letzte reale Kandidatennummer aus der bisherigen (nicht-CRM-) Nummerierung.
# Neue, automatisch vergebene Nummern schließen daran an (ab 4053), damit CRM-
# Kandidaten und die historischen anonymen Profile eine durchgehende Zählung bilden.
_LEGACY_CANDIDATE_NUMBER_FLOOR = 4052


class CandidateService(CrudService[Candidate, CandidateCreate, CandidateUpdate]):
    def __init__(self, session: Session) -> None:
        repository = CandidateRepository(session)
        super().__init__(session, repository, "Candidate")
        self.candidates = repository

    def get(self, entity_id: uuid.UUID) -> Candidate:
        candidate = super().get(entity_id)
        self._attach_ghosting_flags([candidate])
        return candidate

    def update(self, entity_id: uuid.UUID, payload: CandidateUpdate) -> Candidate:
        """Stempelt cv_in_recorded_at, sobald cv_available echt (neu) auf
        True wechselt - einmalig, nie erneut ueberschrieben. Getrennt vom
        reinen Anzeige-Flag cv_available, damit Analytics ("CV In") nur
        echte, ab dem Stichtag neu erfasste CV-Ins zaehlt statt der 2481
        beim Datenuebertrag pauschal gesetzten Alt-Kandidaten (siehe
        Modul-Docstring in models/candidate.py, Nutzer-Feedback 2026-07-15)."""
        was_cv_available = self.get(entity_id).cv_available
        updated = super().update(entity_id, payload)
        if updated.cv_available and not was_cv_available and updated.cv_in_recorded_at is None:
            updated.cv_in_recorded_at = datetime.now(UTC)
            self.session.commit()
        return updated

    def suggest_cv_fields(self, candidate_id: uuid.UUID, cv_text: str) -> CvExtractionSuggestion:
        """Phase M, Punkt 2: schlaegt aus einem hochgeladenen CV nur Felder
        vor, die beim Kandidaten aktuell leer sind - ein vorhandener Wert
        wird nie ueberschrieben, auch nicht als Vorschlag. Der Nutzer
        entscheidet im Frontend, ob er einen Vorschlag uebernimmt."""
        candidate = self.get(candidate_id)
        extracted = extract_candidate_fields(cv_text)

        def suggestion_for(field_name: str, current_value: str | None) -> str | None:
            value = extracted.get(field_name)
            return value if (value and not current_value) else None

        return CvExtractionSuggestion(
            postal_code=suggestion_for("postal_code", candidate.postal_code),
            city=suggestion_for("city", candidate.city),
            phone=suggestion_for("phone", candidate.phone),
            job_title=suggestion_for("job_title", candidate.job_title),
            qualification=suggestion_for("qualification", candidate.qualification),
            ausbildung_titel=suggestion_for("ausbildung_titel", candidate.ausbildung_titel),
            source_is_agency_profile=is_agency_letterhead(cv_text),
        )

    def list_filtered(
        self,
        *,
        status: CandidateStatus | None = None,
        role: str | None = None,
        region: str | None = None,
        search: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[Candidate], int]:
        entities, total = self.candidates.filtered(
            status=status,
            role=role,
            region=region,
            search=search,
            created_from=created_from,
            created_to=created_to,
            offset=offset,
            limit=limit,
        )
        self._attach_ghosting_flags(entities)
        return entities, total

    def reactivation_candidates(self, threshold_months: int | None = None) -> Sequence[Candidate]:
        months = (
            threshold_months
            if threshold_months is not None
            else get_settings().reactivation_threshold_months
        )
        threshold_date = _months_ago(months)
        candidates = self.candidates.stale_contacts(threshold_date)
        self._attach_ghosting_flags(candidates)
        return candidates

    def _attach_ghosting_flags(self, candidates: Sequence[Candidate]) -> None:
        ids = [candidate.id for candidate in candidates]
        ghosting_ids = self.candidates.ghosting_candidate_ids(ids)
        for candidate in candidates:
            candidate.has_ghosting_history = candidate.id in ghosting_ids  # type: ignore[attr-defined]

    def _next_candidate_number(self) -> str:
        """Höchste vorhandene rein numerische candidate_number + 1, mindestens
        _LEGACY_CANDIDATE_NUMBER_FLOOR + 1, damit an die reale Nummerierung
        (zuletzt 4052) angeschlossen wird."""
        numeric_numbers = self.session.scalars(
            select(Candidate.candidate_number).where(Candidate.candidate_number.isnot(None))
        ).all()
        highest = _LEGACY_CANDIDATE_NUMBER_FLOOR
        for value in numeric_numbers:
            if value and value.isdigit():
                highest = max(highest, int(value))
        return str(highest + 1)

    def create(self, payload: CandidateCreate) -> Candidate:
        if not payload.candidate_number:
            payload = payload.model_copy(update={"candidate_number": self._next_candidate_number()})
        return super().create(payload)


def _months_ago(months: int) -> date:
    today = datetime.now(UTC).date()
    return today - timedelta(days=months * 30)
