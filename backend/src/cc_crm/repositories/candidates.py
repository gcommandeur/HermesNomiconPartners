import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import ColumnElement, Integer, String, and_, cast, func, or_, select
from sqlalchemy.orm import Session

from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import Abschlussart, CandidateStatus, Rolle, SubmissionCancellationReason
from cc_crm.models.submission import CandidateSubmission
from cc_crm.repositories.base import SQLAlchemyRepository
from cc_crm.services.synonyms import is_recognized_term, search_expansion_terms

# Dieselben Spalten wie SORT_ACCESSORS in candidates-table.tsx - Sortierung
# muss ueber den gesamten Bestand laufen (ORDER BY), nicht nur ueber die
# aktuell geladene Seite (siehe Kandidaten-Sortier-Bug: bei 30k+ Kandidaten
# sortierte ein Klick auf "Name" bislang nur innerhalb der sichtbaren Zeile).
# candidate_number wird auf Integer gecastet, damit "99" vor "100" einsortiert
# wird statt lexikografisch danach - Kandidatennummern sind durchgehend
# numerische Strings (siehe models/candidate.py::candidate_number).
_SORT_COLUMNS: dict[str, Any] = {
    "candidate_number": cast(Candidate.candidate_number, Integer),
    "name": (Candidate.last_name, Candidate.first_name),
    "job_title": Candidate.job_title,
    "city": func.coalesce(Candidate.city, Candidate.postal_code),
    "salary_expectation": Candidate.salary_expectation,
    "status": Candidate.status,
}


# Freitextsuche (siehe filtered()::search) - Skalarfelder, direkt
# durchsuchbar. current_employer_internal/summary bewusst mit drin: die
# teuer per LLM extrahierten CV-Inhalte sollen ueber die Suche auffindbar
# sein, nicht nur die wenigen Kontaktfelder von vorher.
_SEARCH_TEXT_COLUMNS: tuple[Any, ...] = (
    Candidate.first_name,
    Candidate.last_name,
    Candidate.email,
    Candidate.job_title,
    Candidate.candidate_number,
    Candidate.qualification,
    Candidate.ausbildung_titel,
    Candidate.current_employer_internal,
    Candidate.summary,
)
# JSON-Listenfelder - gleiches CAST-auf-Text-Muster wie beim bestehenden
# rollen/abschluesse-Filter (portabel fuer SQLite UND Postgres, keine
# JSONB/GIN-Migration noetig). Anders als dort OHNE Anfuehrungszeichen um
# den Suchwert: rollen/abschluesse durchsuchen ein festes Vokabular exakt,
# die Freitextsuche hier will bewusst Teiltreffer finden (z.B. "Buchhaltung"
# soll "Finanzbuchhaltung" innerhalb der Liste treffen). berufliche_stationen
# ist eine Liste von Dicts (kanzleityp/kanzleigroesse/...) - der CAST
# serialisiert die komplette JSON-Struktur inkl. Schluesselnamen; ein Treffer
# auf einen Schluesselnamen selbst (z.B. "typ") ist ein bekanntes, in der
# Praxis vernachlaessigbares Risiko (kein gaengiger Suchbegriff).
_SEARCH_JSON_COLUMNS: tuple[Any, ...] = (
    Candidate.fachliche_schwerpunkte,
    Candidate.edv_kenntnisse,
    Candidate.berufliche_stationen,
)

# Deutsche Umlaute/scharfes S auf ihre gaengige ASCII-Transkription
# gefaltet, Bindestrich/Punkt entfernt - sowohl auf den durchsuchten Spalten
# (per SQL) als auch auf jedem Suchbegriff (per Python, siehe
# _normalize_search_term) angewandt, damit z.B. "steuererklarung" (ohne
# Umlaut eingegeben) "Steuererklärung" trifft, ohne die gespeicherten Daten
# anzufassen. Case-Faltung uebernimmt weiterhin lower() (fuer SQLite via
# register_sqlite_unicode_lower bereits Unicode-fest, siehe
# infrastructure/database/session.py) - hier NICHT nochmal dupliziert.
_NORMALIZE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("ä", "ae"),
    ("ö", "oe"),
    ("ü", "ue"),
    ("ß", "ss"),
    ("Ä", "ae"),
    ("Ö", "oe"),
    ("Ü", "ue"),
    # JSON-Listenfelder (fachliche_schwerpunkte/edv_kenntnisse/
    # berufliche_stationen) werden von SQLAlchemy's Standard-JSON-
    # Serialisierung (json.dumps, ensure_ascii=True Default) NICHT als
    # rohes Unicode gespeichert, sondern als \uXXXX-Escape-Sequenz (z.B.
    # "Jahresabschlüsse" -> 'Jahresabschülsse' im gecasteten Text,
    # empirisch verifiziert) - der CAST(...AS TEXT)-Vergleich sieht also
    # diese Escape-Syntax, nicht den Umlaut selbst. Deshalb zusaetzlich zu
    # den rohen Umlaut-Zeichen oben auch deren \uXXXX-Escape-Form falten
    # (Python's json.dumps gibt IMMER kleingeschriebene Hex-Ziffern aus,
    # d.h. nach dem SQL-lower() oben reicht die kleingeschriebene Form).
    # Skalarfelder (ausbildung_titel etc.) sind NIE JSON-serialisiert und
    # enthalten diese Escape-Syntax nie - die zusaetzlichen Ersetzungen
    # sind dort einfach ein No-Op.
    ("\\u00e4", "ae"),
    ("\\u00c4", "ae"),
    ("\\u00f6", "oe"),
    ("\\u00d6", "oe"),
    ("\\u00fc", "ue"),
    ("\\u00dc", "ue"),
    ("\\u00df", "ss"),
    ("-", ""),
    (".", ""),
)


def _normalized_sql_text(column: Any) -> Any:
    """SQL-Gegenstueck zu _normalize_search_term() - wird auf jede
    durchsuchte Spalte angewandt, damit beide Seiten des LIKE-Vergleichs
    gleich normalisiert sind."""
    expr = func.lower(column)
    for old, new in _NORMALIZE_REPLACEMENTS:
        expr = func.replace(expr, old, new)
    return expr


def _normalize_search_term(term: str) -> str:
    normalized = term.lower()
    for old, new in _NORMALIZE_REPLACEMENTS:
        normalized = normalized.replace(old, new)
    return normalized


def _split_search_terms(search: str) -> list[str]:
    """Mehrere durch Leerzeichen getrennte Suchworte -> UND-verknuepfte
    Einzelworte (siehe filtered()::search) - AUSSER die GESAMTE Eingabe ist
    selbst ein bekannter mehrwortiger Synonym-Begriff (z.B. "MS Office",
    "Tax Law"), dann bleibt sie EIN Suchwort (siehe services/synonyms.py::
    is_recognized_term fuer die Begruendung)."""
    cleaned = search.strip()
    if not cleaned:
        return []
    if " " in cleaned and is_recognized_term(cleaned):
        return [cleaned]
    return [t for t in cleaned.split() if t.strip()]


def _search_term_filter(term: str) -> ColumnElement[bool]:
    """EIN Suchwort -> ODER-verknuepfter Treffer in irgendeiner bekannten
    Synonym-/Ober-Unterbegriff-Variante (siehe services/synonyms.py::
    search_expansion_terms) UND irgendeinem der durchsuchten Felder.
    Mehrere Suchworte werden von filtered() UND-verknuepft (siehe dort)."""
    clauses: list[ColumnElement[bool]] = []
    for variant in search_expansion_terms(term):
        pattern = f"%{_normalize_search_term(variant)}%"
        for column in _SEARCH_TEXT_COLUMNS:
            clauses.append(_normalized_sql_text(column).like(pattern))
        for column in _SEARCH_JSON_COLUMNS:
            clauses.append(_normalized_sql_text(cast(column, String)).like(pattern))
    return or_(*clauses)


# Skalarfeld-Namen fuer compute_search_match_fields() - dieselben Felder wie
# _SEARCH_TEXT_COLUMNS oben, hier als Attributname statt InstrumentedAttribute
# (fuer getattr() auf eine bereits geladene Python-Instanz statt fuer eine
# SQL-Spalte).
_SEARCH_TEXT_FIELD_NAMES: tuple[str, ...] = (
    "first_name",
    "last_name",
    "email",
    "job_title",
    "candidate_number",
    "qualification",
    "ausbildung_titel",
    "current_employer_internal",
    "summary",
)
# Listenfelder mit einzelnen, fuer sich sinnvollen Eintraegen (im Unterschied
# zu berufliche_stationen, das als Dict-Liste separat behandelt wird) -
# gematchte Eintraege werden zusaetzlich als "matched_values" zurueckgegeben,
# damit das Frontend genau diesen Eintrag hervorheben kann.
_SEARCH_JSON_FIELD_NAMES: tuple[str, ...] = ("fachliche_schwerpunkte", "edv_kenntnisse")


def compute_search_match_fields(candidate: Candidate, search: str) -> tuple[list[str], list[str]]:
    """Fuer die Nachvollziehbarkeit im Frontend (Punkt 5 des Auftrags
    "Kandidaten-Freitextsuche..."): liefert (matched_fields, matched_values)
    fuer EINEN bereits gefundenen Kandidaten - matched_fields sind die
    Feldnamen, in denen mindestens eines der Suchworte (inkl. Synonym-/
    Ober-Unterbegriff-Varianten) einen Treffer hatte, matched_values sind
    die konkreten fachliche_schwerpunkte/edv_kenntnisse-Eintraege, die
    getroffen haben (fuers Hervorheben der Skill-Badges im Frontend). Wird
    NUR fuer die aktuell zurueckgegebene Seite berechnet (siehe api/v1/
    candidates.py), nicht fuer den gesamten Treffer-Bestand - bei
    Seitengroessen von ~100 vernachlaessigbarer Zusatzaufwand."""
    terms = _split_search_terms(search)
    if not terms:
        return [], []

    matched_fields: list[str] = []
    matched_values: list[str] = []

    def _mark_field(name: str) -> None:
        if name not in matched_fields:
            matched_fields.append(name)

    for term in terms:
        normalized_variants = [_normalize_search_term(v) for v in search_expansion_terms(term)]

        for field_name in _SEARCH_TEXT_FIELD_NAMES:
            raw_value = getattr(candidate, field_name, None)
            if not raw_value:
                continue
            normalized_value = _normalize_search_term(str(raw_value))
            if any(variant in normalized_value for variant in normalized_variants):
                _mark_field(field_name)

        for field_name in _SEARCH_JSON_FIELD_NAMES:
            for entry in getattr(candidate, field_name, None) or []:
                normalized_entry = _normalize_search_term(str(entry))
                if any(variant in normalized_entry for variant in normalized_variants):
                    _mark_field(field_name)
                    if entry not in matched_values:
                        matched_values.append(entry)

        for station in candidate.berufliche_stationen or []:
            station_text = " ".join(
                str(value) for value in station.values() if isinstance(value, str)
            )
            normalized_station_text = _normalize_search_term(station_text)
            if any(variant in normalized_station_text for variant in normalized_variants):
                _mark_field("berufliche_stationen")

    return matched_fields, matched_values


def _order_by_clauses(sort_by: str | None, sort_dir: str) -> list[ColumnElement[Any]]:
    descending = sort_dir == "desc"
    columns: Any = _SORT_COLUMNS.get(sort_by) if sort_by else None
    resolved: tuple[Any, ...]
    if columns is None:
        resolved = (Candidate.last_name, Candidate.first_name)
    elif isinstance(columns, tuple):
        resolved = columns
    else:
        resolved = (columns,)
    return [column.desc() if descending else column.asc() for column in resolved]


class CandidateRepository(SQLAlchemyRepository[Candidate]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Candidate)

    def filtered(
        self,
        *,
        status: CandidateStatus | None = None,
        role: str | None = None,
        rollen: list[Rolle] | None = None,
        abschluesse: list[Abschlussart] | None = None,
        region: str | None = None,
        search: str | None = None,
        owner_user_id: uuid.UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        rollen_unbestaetigt: bool | None = None,
        sort_by: str | None = None,
        sort_dir: str = "asc",
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[Candidate], int]:
        filters = []
        if status is not None:
            filters.append(Candidate.status == status)
        if owner_user_id is not None:
            filters.append(Candidate.owner_user_id == owner_user_id)
        if role:
            filters.append(Candidate.job_title.ilike(f"%{role}%"))
        if rollen:
            # Candidate.rollen bleibt bewusst sa.JSON (kein JSONB/GIN, siehe
            # Kommentar dort) - Containment daher ueber CAST auf Text +
            # Substring-Match auf den quotierten Wert (z.B. '"partner"'),
            # damit z.B. "partner" nicht faelschlich "hauptpartner" traefe.
            # Portabel fuer SQLite (lokale Entwicklung) UND Postgres
            # (Produktion), da beide JSON als Text serialisieren/casten
            # koennen - anders als json_contains()/@>, die dialektspezifisch
            # waeren. Mehrere angegebene Rollen sind ODER-verknuepft (ein
            # Kandidat mit IRGENDEINER der gewaehlten Rollen matcht).
            rollen_text = cast(Candidate.rollen, String)
            filters.append(
                or_(*(rollen_text.contains(f'"{value.value}"') for value in rollen))
            )
        if abschluesse:
            # Gleiches Muster wie rollen oben (JSON-Liste, kein JSONB/GIN) -
            # ODER-verknuepft, ein Kandidat mit IRGENDEINER der gewaehlten
            # Abschlussarten matcht.
            abschluesse_text = cast(Candidate.abschluesse, String)
            filters.append(
                or_(*(abschluesse_text.contains(f'"{value.value}"') for value in abschluesse))
            )
        if region:
            filters.append(
                or_(Candidate.city.ilike(f"%{region}%"), Candidate.postal_code.ilike(f"%{region}%"))
            )
        if search:
            # Mehrere durch Leerzeichen getrennte Suchworte sind UND-
            # verknuepft (z.B. "DATEV Lohnbuchhaltung" -> nur Kandidaten mit
            # BEIDEM), innerhalb eines Suchworts gilt ODER ueber alle
            # Synonym-/Ober-Unterbegriff-Varianten UND alle durchsuchten
            # Felder (siehe _search_term_filter oben).
            search_terms = _split_search_terms(search)
            if search_terms:
                filters.append(and_(*(_search_term_filter(t) for t in search_terms)))
        if created_from:
            filters.append(Candidate.created_at >= created_from)
        if created_to:
            filters.append(Candidate.created_at <= created_to)
        if rollen_unbestaetigt is not None:
            # Titelschutz-Korrektur Schritt 2: eigener Filter, um genau die
            # markierten Kandidaten wiederzufinden (Nutzer-Vorgabe -
            # "sonst findet man sie nicht wieder").
            filters.append(Candidate.rollen_unbestaetigt == rollen_unbestaetigt)
        query = (
            select(Candidate)
            .where(*filters)
            .order_by(*_order_by_clauses(sort_by, sort_dir))
            .offset(offset)
            .limit(limit)
        )
        count = select(func.count()).select_from(Candidate).where(*filters)
        return self.session.scalars(query).all(), int(self.session.scalar(count) or 0)

    def ghosting_candidate_ids(self, candidate_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        """IDs aus candidate_ids, die mindestens eine mit candidate_ghosting
        abgebrochene Submission haben (Basis für den Ghosting-Badge)."""
        if not candidate_ids:
            return set()
        rows = self.session.scalars(
            select(CandidateSubmission.candidate_id)
            .where(
                CandidateSubmission.candidate_id.in_(candidate_ids),
                CandidateSubmission.cancellation_reason
                == SubmissionCancellationReason.CANDIDATE_GHOSTING,
            )
            .distinct()
        ).all()
        return set(rows)

    def stale_contacts(self, threshold_date: date) -> Sequence[Candidate]:
        """Kandidaten mit einem gesetzten last_contact_at, das älter als
        threshold_date ist, sortiert nach längster Inaktivität zuerst -
        Grundlage der Reaktivierungsliste."""
        query = (
            select(Candidate)
            .where(
                Candidate.last_contact_at.isnot(None),
                Candidate.last_contact_at < threshold_date,
            )
            .order_by(Candidate.last_contact_at.asc())
        )
        return self.session.scalars(query).all()
