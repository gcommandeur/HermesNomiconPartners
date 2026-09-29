"""Vakanz -> Kandidaten-Matching (Gegenstueck zu services/matching.py, das
Kandidat -> Kanzleien matcht). Gleiches Token-Ueberlappungs-Prinzip, aber mit
zwei zusaetzlichen, laut Nutzer-Vorgabe deutlich staerker gewichteten
Kriterien: Rolle (JobMandate.title vs. Candidate.job_title) und Region
(JobMandate.location + search_radius_km vs. Candidate.city/postal_code).
Kandidaten ausserhalb des Umkreises werden nicht nur abgewertet, sondern ganz
ausgeschlossen (siehe find_matches) - nur, wenn der Umkreis ueberhaupt
berechenbar ist (beide Seiten muessen sich auf eine bekannte Stadt/PLZ-Zone
aufloesen lassen, siehe services/geo.py::resolve_place_query/candidate_coordinates);
ist er nicht berechenbar, bleibt der Kandidat regulaer (ohne Regions-Bonus)
im Ergebnis, statt ihn wegen fehlender Daten faelschlich auszuschliessen."""

import re
import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import CandidateStatus
from cc_crm.models.job_mandate import JobMandate
from cc_crm.schemas.candidate import CandidateRead
from cc_crm.schemas.vacancy_matching import CandidateMatchRead
from cc_crm.services.candidates import CandidateService
from cc_crm.services.geo import (
    PostalLocalityIndex,
    candidate_coordinates,
    haversine_km,
    load_postal_locality_index,
    resolve_place_query,
)
from cc_crm.services.jobs import JobMandateService
from cc_crm.services.matching import _tokens

EXCLUDED_CANDIDATE_STATUSES = {CandidateStatus.BLOCKED, CandidateStatus.ARCHIVED}

ROLE_EXACT_BONUS = 15
ROLE_PARTIAL_BONUS = 7
REGION_IN_RADIUS_BONUS = 12
GENERIC_TOKEN_WEIGHT = 1

_GENDER_SUFFIX_RE = re.compile(r"\((?:[mwd]\s*/\s*)*[mwd]\)", re.IGNORECASE)
_NON_WORD_RE = re.compile(r"[^\wäöüÄÖÜß\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_role(value: str | None) -> str:
    if not value:
        return ""
    cleaned = _GENDER_SUFFIX_RE.sub("", value)
    cleaned = _NON_WORD_RE.sub(" ", cleaned)
    return _WHITESPACE_RE.sub(" ", cleaned).strip().lower()


def _role_score(job_title: str, candidate_job_title: str | None) -> tuple[int, str | None]:
    job_norm = _normalize_role(job_title)
    cand_norm = _normalize_role(candidate_job_title)
    if not job_norm or not cand_norm:
        return 0, None
    if job_norm == cand_norm:
        return ROLE_EXACT_BONUS, "Rolle stimmt exakt überein"
    job_role_tokens = _tokens(job_norm)
    cand_role_tokens = _tokens(cand_norm)
    if job_role_tokens and job_role_tokens <= cand_role_tokens:
        # Alle Woerter der Vakanz-Rolle stecken in der Kandidaten-Rolle (z.B.
        # Vakanz "Steuerberater" vollstaendig in Kandidat "Senior
        # Steuerberater") - zaehlt wie ein Treffer, nicht nur Teilweise.
        return ROLE_EXACT_BONUS, "Rolle passt (inkl. Zusatz)"
    overlap = job_role_tokens & cand_role_tokens
    if overlap:
        return ROLE_PARTIAL_BONUS, "Rolle teilweise passend: " + ", ".join(sorted(overlap))
    return 0, None


class VacancyMatchingService:
    """Findet Kandidaten, die plausibel zu einer Vakanz passen - Gegenstueck
    zu CandidateMatchingService (Kandidat -> Kanzleien)."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.jobs = JobMandateService(session)
        self.candidates = CandidateService(session)

    def find_matches(self, job_id: uuid.UUID, *, limit: int = 50) -> list[CandidateMatchRead]:
        job = self.jobs.get(job_id)
        job_tokens = _tokens(job.title, job.qualifications, job.description, *(job.must_have or []))
        job_lat, job_lng, job_precise = resolve_place_query(self.session, job.location)
        if not job_precise:
            # Nur ueber die grobe PLZ_ZONE_COORDINATES-Naeherung aufloesbar
            # (kann 100+ km danebenliegen, siehe geo.py::resolve_place_query-
            # Docstring) - fuer den Umkreis-Filter unten wie "gar nicht
            # aufloesbar" behandeln, sonst koennten Kandidaten anhand eines
            # strukturell falsch verorteten Vakanz-Zentrums faelschlich
            # ausgeschlossen werden.
            job_lat, job_lng = None, None

        candidates: Sequence[Candidate] = self.candidates.list(offset=0, limit=5000)

        # EINMAL pro Matching-Lauf geladen statt pro Kandidat eine eigene
        # DB-Query (N+1-Query-Problem, siehe geo.py::PostalLocalityIndex-
        # Docstring) - nur, wenn ueberhaupt ein Vakanz-Zentrum aufloesbar
        # ist, sonst wird _score() die Koordinate ohnehin nie nachschlagen.
        index = load_postal_locality_index(self.session) if job_lat is not None else None

        matches: list[CandidateMatchRead] = []
        for candidate in candidates:
            if candidate.status in EXCLUDED_CANDIDATE_STATUSES:
                continue
            score, reasons, in_radius = self._score(
                self.session, job, job_tokens, job_lat, job_lng, candidate, index
            )
            if in_radius is False:
                # Ausserhalb des Vakanz-Umkreises und beide Seiten hatten
                # aufloesbare Koordinaten - laut Nutzer-Vorgabe ausschliessen,
                # nicht nur herunterstufen.
                continue
            matches.append(
                CandidateMatchRead(
                    candidate=CandidateRead.model_validate(candidate),
                    score=score,
                    reasons=reasons,
                    in_radius=in_radius,
                )
            )

        matches.sort(key=lambda match: (-match.score, match.candidate.last_name))
        return matches[:limit]

    @staticmethod
    def _score(
        session: Session,
        job: JobMandate,
        job_tokens: set[str],
        job_lat: float | None,
        job_lng: float | None,
        candidate: Candidate,
        index: PostalLocalityIndex | None = None,
    ) -> tuple[int, list[str], bool | None]:
        score = 0
        reasons: list[str] = []

        role_score, role_reason = _role_score(job.title, candidate.job_title)
        if role_reason:
            score += role_score
            reasons.append(role_reason)

        in_radius: bool | None = None
        if job_lat is not None and job_lng is not None:
            # apply_jitter=False: keine Kartenversatz-Streuung in einer
            # Distanzberechnung fuer einen Umkreis-Filter (siehe geo.py::
            # candidate_coordinates-Docstring). precise=False (nur ueber die
            # grobe Zonen-Naeherung aufloesbar) zaehlt wie "gar nicht
            # aufloesbar" - der Kandidat bleibt dann regulaer (ohne Regions-
            # Bonus) im Ergebnis, statt anhand einer 100+ km ungenauen
            # Koordinate faelschlich aus- oder eingeschlossen zu werden.
            cand_lat, cand_lng, cand_precise = candidate_coordinates(
                session,
                candidate.city,
                candidate.postal_code,
                str(candidate.id),
                apply_jitter=False,
                index=index,
            )
            if cand_lat is not None and cand_lng is not None and cand_precise:
                distance_km = haversine_km(job_lat, job_lng, cand_lat, cand_lng)
                in_radius = distance_km <= job.search_radius_km
                if in_radius:
                    score += REGION_IN_RADIUS_BONUS
                    reasons.append(f"Im Umkreis ({round(distance_km)} km)")

        candidate_tokens = _tokens(
            candidate.job_title, candidate.qualification, *(candidate.fachliche_schwerpunkte or [])
        )
        overlap = job_tokens & candidate_tokens
        if overlap:
            score += GENERIC_TOKEN_WEIGHT * len(overlap)
            reasons.append("Passt zu: " + ", ".join(sorted(overlap)))

        return score, reasons, in_radius
