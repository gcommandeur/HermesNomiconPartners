"""Sourcing-Agent: legt automatisiert gefundene Personen als SourcingLead an
(Review-Ebene) und ueberfuehrt sie erst nach expliziter menschlicher
Bestaetigung in echte Candidate-Datensaetze.

Fuzzy-Namensabgleich gegen den bestehenden Kandidatenbestand: bewusst mit
difflib (Standardbibliothek) statt einer neuen Dependency wie rapidfuzz
umgesetzt - gleiches Vorgehen wie beim bestehenden Kanzlei-Namensvergleich
(services/name_matching.py). token_sort-Verhalten wird durch alphabetisches
Sortieren der Namens-Tokens vor dem Vergleich erreicht, so dass
"Müller, Hans" und "Hans Müller" als identisch erkannt werden."""

import re
import unicodedata
import uuid
from datetime import UTC, datetime
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import SourcingLeadStatus, SourcingSourceType
from cc_crm.models.sourcing_lead import SourcingLead
from cc_crm.schemas.candidate import CandidateCreate
from cc_crm.schemas.sourcing import SourcingLeadCreate
from cc_crm.services.candidates import CandidateService

# Schwelle analog zur Nutzer-Vorgabe (~90 bei rapidfuzz.token_sort_ratio,
# dort 0-100 skaliert) - Personennamen sind kurz, unterhalb von 0.9 haeufen
# sich falsch-positive Treffer (z.B. "Meier"/"Maier" verschiedener Personen
# ist dagegen genau der gewollte Graubereich knapp ueber der Schwelle).
NAME_SIMILARITY_THRESHOLD = 0.90

_NON_LETTER_RE = re.compile(r"[^a-z0-9 ]")
_WHITESPACE_RE = re.compile(r"\s+")

# Akademische Titel/Berufsbezeichnungen, die Verzeichnisse haeufig in das
# Namensfeld mischen ("Dr. Hans Müller", "Hans Müller StB") - fuer den
# Personenvergleich irrelevant und deshalb vor dem Matching entfernt.
_TITLE_RE = re.compile(
    r"\b(prof|dr|dipl|kfm|kffr|ing|oec|jur|rer|pol|nat|habil|mba|llm|ll|m|b|a|"
    r"stb|stbin|wp|wpin|ra|rain|mag)\b\.?",
    re.IGNORECASE,
)


def normalize_person_name(first_name: str, last_name: str) -> str:
    """Titel entfernen, Umlaute/Akzente vereinheitlichen (Müller == Mueller ==
    Muller), Tokens alphabetisch sortieren (token_sort: Reihenfolge von Vor-/
    Nachname egal)."""
    value = f"{first_name} {last_name}".casefold()
    value = _TITLE_RE.sub(" ", value)
    value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = _NON_LETTER_RE.sub(" ", value)
    value = _WHITESPACE_RE.sub(" ", value).strip()
    return " ".join(sorted(value.split(" ")))


def person_name_similarity(a: str, b: str) -> float:
    """0.0-1.0 auf bereits normalisierten (token-sortierten) Namen."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


class SourcingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        # Kandidaten-Namensliste wird pro Service-Instanz (== pro Request/
        # Sourcing-Lauf) genau einmal geladen statt bei jedem create_lead
        # erneut - ein Lauf legt leicht hunderte Leads am Stueck an.
        self._candidate_names: list[tuple[uuid.UUID, str]] | None = None

    def list_leads(
        self,
        *,
        status: SourcingLeadStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[SourcingLead], int]:
        query = select(SourcingLead)
        if status is not None:
            query = query.where(SourcingLead.status == status)
        total = len(self.session.scalars(query.with_only_columns(SourcingLead.id)).all())
        leads = self.session.scalars(
            query.order_by(SourcingLead.found_at.desc()).offset(offset).limit(limit)
        ).all()
        return list(leads), total

    def get_lead(self, lead_id: uuid.UUID) -> SourcingLead:
        lead = self.session.get(SourcingLead, lead_id)
        if lead is None:
            raise EntityNotFoundError("Sourcing lead not found")
        return lead

    def create_lead(self, payload: SourcingLeadCreate) -> SourcingLead | None:
        """Legt einen Lead an - oder gibt None zurueck, wenn fuer dieselbe
        Person aus derselben Quelle bereits ein Lead existiert (verhindert
        Doppel-Leads bei wiederholten Sourcing-Laeufen). Ein Fuzzy-Treffer
        gegen den bestehenden Kandidatenbestand verhindert das Anlegen NICHT,
        sondern markiert den Lead als POSSIBLE_DUPLICATE mit Verweis auf den
        Kandidaten - der Mensch entscheidet im Review (koennte z.B. ein
        Arbeitgeberwechsel eines Bestandskandidaten sein)."""
        if self._lead_exists(payload.first_name, payload.last_name, payload.source_type):
            return None

        status = SourcingLeadStatus.PENDING
        duplicate_of: uuid.UUID | None = None
        match = self._find_similar_candidate(payload.first_name, payload.last_name)
        if match is not None:
            status = SourcingLeadStatus.POSSIBLE_DUPLICATE
            duplicate_of = match

        lead = SourcingLead(
            **payload.model_dump(),
            status=status,
            duplicate_of_candidate_id=duplicate_of,
            found_at=datetime.now(UTC),
        )
        self.session.add(lead)
        self.session.commit()
        self.session.refresh(lead)
        return lead

    def approve_lead(self, lead_id: uuid.UUID, user_id: uuid.UUID) -> SourcingLead:
        """Erstellt aus dem Lead einen echten Kandidaten ueber den bestehenden
        CandidateService.create() (gleiche Validierung/Nummernvergabe wie beim
        regulaeren Anlegen - bewusst wiederverwendet statt dupliziert)."""
        lead = self.get_lead(lead_id)
        self._ensure_reviewable(lead)
        candidate = CandidateService(self.session).create(
            CandidateCreate(
                first_name=lead.first_name,
                last_name=lead.last_name,
                city=lead.city,
                postal_code=lead.postal_code,
                summary=self._source_summary(lead),
                owner_user_id=user_id,
            )
        )
        lead.status = SourcingLeadStatus.APPROVED
        lead.created_candidate_id = candidate.id
        self._stamp_review(lead, user_id)
        return lead

    def reject_lead(self, lead_id: uuid.UUID, user_id: uuid.UUID) -> SourcingLead:
        lead = self.get_lead(lead_id)
        self._ensure_reviewable(lead)
        lead.status = SourcingLeadStatus.REJECTED
        self._stamp_review(lead, user_id)
        return lead

    @staticmethod
    def _ensure_reviewable(lead: SourcingLead) -> None:
        if lead.status not in (SourcingLeadStatus.PENDING, SourcingLeadStatus.POSSIBLE_DUPLICATE):
            raise BusinessRuleError(f"Lead wurde bereits bearbeitet (Status: {lead.status.value})")

    def _stamp_review(self, lead: SourcingLead, user_id: uuid.UUID) -> None:
        lead.reviewed_at = datetime.now(UTC)
        lead.reviewed_by_user_id = user_id
        self.session.commit()
        self.session.refresh(lead)

    @staticmethod
    def _source_summary(lead: SourcingLead) -> str:
        parts = [f"Via Sourcing-Agent gefunden (Quelle: {lead.source_type.value})"]
        if lead.current_employer:
            parts.append(f"Arbeitgeber laut Quelle: {lead.current_employer}")
        if lead.source_url:
            parts.append(lead.source_url)
        return "\n".join(parts)

    def _lead_exists(
        self, first_name: str, last_name: str, source_type: SourcingSourceType
    ) -> bool:
        normalized = normalize_person_name(first_name, last_name)
        existing = self.session.scalars(
            select(SourcingLead).where(SourcingLead.source_type == source_type)
        ).all()
        return any(
            normalize_person_name(lead.first_name, lead.last_name) == normalized
            for lead in existing
        )

    def _find_similar_candidate(self, first_name: str, last_name: str) -> uuid.UUID | None:
        normalized = normalize_person_name(first_name, last_name)
        if not normalized:
            return None
        best_id: uuid.UUID | None = None
        best_score = 0.0
        for candidate_id, candidate_name in self._candidate_name_index():
            score = person_name_similarity(normalized, candidate_name)
            if score >= NAME_SIMILARITY_THRESHOLD and score > best_score:
                best_id = candidate_id
                best_score = score
        return best_id

    def _candidate_name_index(self) -> list[tuple[uuid.UUID, str]]:
        if self._candidate_names is None:
            rows = self.session.execute(
                select(Candidate.id, Candidate.first_name, Candidate.last_name)
            ).all()
            self._candidate_names = [
                (row[0], normalize_person_name(row[1], row[2])) for row in rows
            ]
        return self._candidate_names
