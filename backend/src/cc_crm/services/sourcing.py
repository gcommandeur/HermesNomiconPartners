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
import time
import unicodedata
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from difflib import SequenceMatcher

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import AIProviderError, BusinessRuleError, EntityNotFoundError
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import Rolle, SourcingLeadStatus, SourcingRunStatus, SourcingSourceType
from cc_crm.models.sourcing_lead import SourcingLead
from cc_crm.models.sourcing_run import SourcingRun
from cc_crm.schemas.candidate import CandidateCreate
from cc_crm.schemas.note import NoteCreate
from cc_crm.schemas.sourcing import SourcingLeadCreate, SourcingRunResult
from cc_crm.services import kanzlei_team_scrape, steuerberater_verzeichnis, wpk_berufsregister
from cc_crm.services.candidates import CandidateService
from cc_crm.services.cv_extraction import derive_rollen_from_text
from cc_crm.services.geo import (
    candidate_coordinates,
    haversine_km,
    load_postal_locality_index,
    postal_codes_within_radius,
    resolve_place_query,
)
from cc_crm.services.name_matching import (
    SIMILARITY_THRESHOLD,
    name_similarity,
    normalize_company_name,
)
from cc_crm.services.notes import NoteService
from cc_crm.services.steuerberater_verzeichnis import TooManyResultsError

# Schwelle analog zur Nutzer-Vorgabe (~90 bei rapidfuzz.token_sort_ratio,
# dort 0-100 skaliert) - Personennamen sind kurz, unterhalb von 0.9 haeufen
# sich falsch-positive Treffer (z.B. "Meier"/"Maier" verschiedener Personen
# ist dagegen genau der gewollte Graubereich knapp ueber der Schwelle).
NAME_SIMILARITY_THRESHOLD = 0.90

# Pause zwischen zwei Verzeichnis-Requests (hoefliches Crawling gegenueber
# der oeffentlichen Behoerdenseite - keine Parallel-Anfragen, ein Request
# pro PLZ/Ort mit Abstand).
DIRECTORY_REQUEST_PAUSE_SECONDS = 1.5
# Kurze Pause zwischen zwei Seiten-Abrufen DERSELBEN Kanzlei-Website beim
# Team-Scrape (Startseite -> Team-Unterseite).
TEAM_PAGE_FETCH_PAUSE_SECONDS = 0.5


def _steuerberater_notes_text(person: steuerberater_verzeichnis.DirectoryPerson) -> str:
    """Strukturierte Zusammenfassung aus dem amtlichen Verzeichnis (keine
    freie Bio verfuegbar, nur offizielle Registerdaten) - wird bei approve als
    Note am Kandidaten hinterlegt, damit nach der Uebernahme nachvollziehbar
    bleibt, woher die Person stammt und was laut Quelle ihre Rolle ist."""
    lines = [f"Bestellt als {person.beruf} laut amtlichem Steuerberaterverzeichnis."]
    if person.akademische_grade:
        lines.append(f"Akademischer Grad: {person.akademische_grade}")
    if person.employer:
        lines.append(f"Kanzlei laut Quelle: {person.employer}")
    if person.address_lines:
        lines.append("Adresse laut Quelle: " + ", ".join(person.address_lines))
    return "\n".join(lines)


def _wpk_notes_text(person: wpk_berufsregister.WpkPerson) -> str:
    """Analog zu _steuerberater_notes_text fuer das WPK-Berufsregister."""
    lines = [f"Bestellt als {person.beruf} laut WPK-Berufsregister."]
    if person.akademische_grade:
        lines.append(f"Akademischer Grad: {person.akademische_grade}")
    if person.street or person.postal_code or person.city:
        plz_ort = f"{person.postal_code or ''} {person.city or ''}".strip()
        address = ", ".join(part for part in (person.street, plz_ort) if part)
        lines.append(f"Adresse laut Quelle: {address}")
    if person.registernummer:
        lines.append(f"Registernummer: {person.registernummer}")
    return "\n".join(lines)


# Wird beim Approve genutzt, um aus lead.raw_data einen Titel/Fachgebiet-Text
# zu ziehen - je nach Quelle unter unterschiedlichem Schluessel abgelegt
# (siehe raw_data= in run_steuerberater_search/run_wpk_search: "beruf";
# run_kanzlei_team_scrape: "title"). Es gibt bewusst KEINE eigene Spalte
# "quelle-titel" auf SourcingLead - raw_data ist schemalos, genau dafuer da.
_JOB_TITLE_RAW_DATA_KEYS = ("beruf", "title")

# Telefonnummer wird nur uebernommen, wenn eine Quelle sie tatsaechlich
# liefert - Stand jetzt liefert KEINE der drei angebundenen Quellen
# (steuerberater_verzeichnis.py, wpk_berufsregister.py, kanzlei_team_scrape.py)
# eine Telefonnummer im raw_data (verifiziert gegen deren aktuelle
# raw_data=-Aufrufe oben) - dieser generische Schluessel-Check ist bewusst
# zukunftsoffen fuer eine spaetere Quelle, die das liefert, statt tot Code zu
# sein: er greift automatisch, sobald raw_data["phone"]/["telefon"] irgendwo
# gesetzt wird.
_PHONE_RAW_DATA_KEYS = ("phone", "telefon")

def _job_title_from_raw_data(raw_data: dict[str, object] | None) -> str | None:
    """Titel/Fachgebiet aus dem schemalosen raw_data - Schluesselname je nach
    Quelle unterschiedlich, siehe _JOB_TITLE_RAW_DATA_KEYS."""
    if not raw_data:
        return None
    for key in _JOB_TITLE_RAW_DATA_KEYS:
        value = raw_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _phone_from_raw_data(raw_data: dict[str, object] | None) -> str | None:
    """Siehe _PHONE_RAW_DATA_KEYS - liefert aktuell bei keiner Quelle einen
    Treffer, greift aber automatisch, sobald eine Quelle das nachliefert."""
    if not raw_data:
        return None
    for key in _PHONE_RAW_DATA_KEYS:
        value = raw_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _rollen_from_text(text: str | None) -> list[Rolle]:
    """Duenner Wrapper um cv_extraction.py::derive_rollen_from_text (dort
    liegt die Logik jetzt zentral, damit Erstellen/Bearbeiten/Sourcing/
    Backfill dieselbe Ableitung nutzen, siehe Modul-Kommentar dort) - liefert
    bewusst eine leere Liste statt zu raten, wenn kein Schluesselwort trifft
    (z.B. WPKs "vereidigte/r Buchprüfer/in", das keiner der 10 Rolle-
    Kategorien exakt entspricht)."""
    return [Rolle(value) for value in derive_rollen_from_text(text)]


def _team_page_notes_text(member: kanzlei_team_scrape.TeamMember) -> str | None:
    """Rolle + per LLM extrahierte Stellenbeschreibung/Werdegang von der
    Team-Seite - None nur, wenn die Seite ueberhaupt nichts ueber die Person
    hergibt (dann bleibt notes_text leer statt einer leeren Note)."""
    parts = [part for part in (member.title, member.info_text) if part]
    return "\n".join(parts) if parts else None


def _merge_results(total: "SourcingRunResult", partial: "SourcingRunResult") -> None:
    total.found += partial.found
    total.created += partial.created
    total.skipped_existing += partial.skipped_existing
    total.possible_duplicates += partial.possible_duplicates
    total.errors.extend(partial.errors)


def scan_team_pages_in_background(client_company_ids: list[uuid.UUID], run_id: uuid.UUID) -> None:
    """FastAPI-BackgroundTask fuer "alle erfassten Kanzleien scannen": laeuft
    nach der HTTP-Antwort mit eigener DB-Session weiter (die Request-Session
    ist dann bereits geschlossen). Ergebnisse erscheinen fortlaufend als
    Leads auf der /sourcing-Seite; Fehler einzelner Kanzleien brechen den
    Scan nicht ab.

    Prueft vor JEDER Kanzlei den stop_requested-Flag des zugehoerigen
    SourcingRun (per POST /sourcing/stop von aussen gesetzt) und bricht dann
    ab - ein bereits laufender Website-/LLM-Request fuer die aktuelle
    Kanzlei wird nicht mitten drin abgebrochen, erst die naechste Iteration
    startet nicht mehr. DB-gestuetzt statt In-Memory-Flag, da Stop-Kommando
    und Hintergrund-Lauf in unterschiedlichen Sessions/Requests laufen."""
    _process_in_background(
        run_id,
        client_company_ids,
        lambda service, company_id: service.run_kanzlei_team_scrape(company_id),
    )


def search_areas_in_background(
    source_type: SourcingSourceType, postal_codes: list[str], run_id: uuid.UUID
) -> None:
    """Umkreissuche der Verzeichnis-Quellen: eine Anfrage pro PLZ im Umkreis,
    mit demselben Fortschritt/Stop-Mechanismus wie der Team-Scan."""

    def step(service: "SourcingService", postal_code: str) -> SourcingRunResult:
        if source_type == SourcingSourceType.STEUERBERATERVERZEICHNIS:
            return service.run_steuerberater_search(postal_code)
        return service.run_wpk_search(postal_code)

    _process_in_background(run_id, postal_codes, step)


def _process_in_background[T](
    run_id: uuid.UUID,
    items: list[T],
    step: Callable[["SourcingService", T], SourcingRunResult],
) -> None:
    from cc_crm.infrastructure.database.session import SessionLocal

    with SessionLocal() as session:
        service = SourcingService(session)
        run = session.get(SourcingRun, run_id)
        if run is None:
            return
        for index, item in enumerate(items):
            if index > 0:
                time.sleep(DIRECTORY_REQUEST_PAUSE_SECONDS)
            session.refresh(run)
            if run.stop_requested:
                run.status = SourcingRunStatus.STOPPED
                run.finished_at = datetime.now(UTC)
                session.commit()
                return
            result = step(service, item)
            run.processed = index + 1
            run.leads_created += result.created
            session.commit()
        run.status = SourcingRunStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        session.commit()


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
        self._lead_names: dict[SourcingSourceType, set[str]] = {}
        self._client_company_names: list[tuple[uuid.UUID, str]] | None = None

    def start_run(self, source_type: SourcingSourceType, total: int) -> SourcingRun:
        run = SourcingRun(source_type=source_type, status=SourcingRunStatus.RUNNING, total=total)
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def get_run_status(self) -> SourcingRun | None:
        """Neuester Lauf ueberhaupt (laufend oder zuletzt beendet) - genau
        einer zur Zeit, da scan_all_companies serialisiert ueber alle
        Kanzleien laeuft."""
        return self.session.scalars(
            select(SourcingRun).order_by(SourcingRun.started_at.desc()).limit(1)
        ).first()

    def request_stop(self) -> SourcingRun:
        run = self.session.scalars(
            select(SourcingRun)
            .where(SourcingRun.status == SourcingRunStatus.RUNNING)
            .order_by(SourcingRun.started_at.desc())
            .limit(1)
        ).first()
        if run is None:
            raise EntityNotFoundError("Kein laufender Sourcing-Lauf gefunden")
        run.stop_requested = True
        self.session.commit()
        self.session.refresh(run)
        return run

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
        self._lead_name_index(payload.source_type).add(
            normalize_person_name(payload.first_name, payload.last_name)
        )
        return lead

    def run_steuerberater_search(self, plz_or_ort: str) -> SourcingRunResult:
        """Ein Verzeichnis-Request fuer EINE PLZ bzw. EINEN Ort: Ergebnisliste
        parsen und jeden Personen-Treffer als Lead anlegen (mit der ueblichen
        Doppel-Lead-/Kandidaten-Duplikat-Pruefung aus create_lead)."""
        result = SourcingRunResult()
        try:
            html = steuerberater_verzeichnis.fetch_search_html(plz_or_ort)
            persons = steuerberater_verzeichnis.parse_persons(html)
        except TooManyResultsError as exception:
            result.errors.append(f"{plz_or_ort}: {exception}")
            return result
        except httpx.HTTPError as exception:
            result.errors.append(f"{plz_or_ort}: Verzeichnis nicht erreichbar ({exception})")
            return result
        result.found = len(persons)
        for person in persons:
            matched_company = self._match_client_company(person.employer)
            # Wenn wir die Kanzlei bereits im CRM kennen, gilt deren
            # (normalisierte) Adresse als verlaesslicher als die aus dem
            # Verzeichnis-Freitext geparste - Fallback bleibt die
            # Verzeichnis-Adresse, falls die Kanzlei keine PLZ/Ort hinterlegt hat.
            city = (matched_company.city if matched_company else None) or person.city
            postal_code = (
                matched_company.postal_code if matched_company else None
            ) or person.postal_code
            self._record_lead_result(
                result,
                SourcingLeadCreate(
                    source_type=SourcingSourceType.STEUERBERATERVERZEICHNIS,
                    source_url=person.detail_url,
                    first_name=person.first_name,
                    last_name=person.last_name,
                    current_employer=person.employer,
                    city=city,
                    postal_code=postal_code,
                    matched_client_company_id=matched_company.id if matched_company else None,
                    raw_data={
                        "beruf": person.beruf,
                        "akademische_grade": person.akademische_grade,
                        "street": person.street,
                        "address_lines": person.address_lines,
                        "suchbegriff": plz_or_ort,
                    },
                    notes_text=_steuerberater_notes_text(person),
                ),
            )
        return result

    def run_wpk_search(self, plz_or_ort: str) -> SourcingRunResult:
        """Analog zu run_steuerberater_search, Quelle WPK-Berufsregister
        (strukturierte JSON-Antwort statt HTML, siehe wpk_berufsregister.py).

        Geprueft (Auftrag "WPK-Arbeitgeber-Matching"): OHNE
        _match_client_company()-Aufruf hier, anders als run_steuerberater_search
        oben - das WPK-Berufsregister liefert in seiner Antwort schlicht KEINEN
        Arbeitgeber-/Kanzleinamen (siehe WpkPerson-Dataclass und die am
        2026-07-23 live verifizierte Fixture in
        tests/services/test_wpk_berufsregister.py: nur Name, Adresse,
        Registernummer, Berufsklassifizierung WP/vBP - keine Kanzlei). Es gibt
        also nichts, das sich gegen ClientCompany fuzzy-matchen liesse, ohne
        Daten zu erfinden - anders als beim Steuerberaterverzeichnis (liefert
        person.employer) oder beim Team-Seiten-Scrape (matched_client_company_id
        ist dort trivialerweise gesetzt, da von der Kanzlei aus gestartet wird)."""
        result = SourcingRunResult()
        try:
            rows = wpk_berufsregister.fetch_search_results(plz_or_ort)
            persons = wpk_berufsregister.parse_persons(rows)
        except httpx.HTTPError as exception:
            result.errors.append(f"{plz_or_ort}: WPK-Register nicht erreichbar ({exception})")
            return result
        result.found = len(persons)
        for person in persons:
            self._record_lead_result(
                result,
                SourcingLeadCreate(
                    source_type=SourcingSourceType.WPK_BERUFSREGISTER,
                    source_url=wpk_berufsregister.REGISTER_URL,
                    first_name=person.first_name,
                    last_name=person.last_name,
                    city=person.city,
                    postal_code=person.postal_code,
                    raw_data={
                        "beruf": person.beruf,
                        "akademische_grade": person.akademische_grade,
                        "street": person.street,
                        "registernummer": person.registernummer,
                        "suchbegriff": plz_or_ort,
                    },
                    notes_text=_wpk_notes_text(person),
                ),
            )
        return result

    def run_area_searches(
        self, source_type: SourcingSourceType, plz_or_ort_list: list[str]
    ) -> SourcingRunResult:
        """Sequenzieller Lauf ueber mehrere PLZ/Orte mit Pause zwischen den
        Requests (hoefliches Crawling, siehe DIRECTORY_REQUEST_PAUSE_SECONDS).
        Fehler einzelner Gebiete brechen den Lauf nicht ab, sondern landen
        gesammelt in errors."""
        run_single = (
            self.run_steuerberater_search
            if source_type == SourcingSourceType.STEUERBERATERVERZEICHNIS
            else self.run_wpk_search
        )
        total = SourcingRunResult()
        for index, value in enumerate(plz_or_ort_list):
            if index > 0:
                time.sleep(DIRECTORY_REQUEST_PAUSE_SECONDS)
            _merge_results(total, run_single(value))
        return total

    def run_steuerberater_searches(self, plz_or_ort_list: list[str]) -> SourcingRunResult:
        return self.run_area_searches(SourcingSourceType.STEUERBERATERVERZEICHNIS, plz_or_ort_list)

    def run_kanzlei_team_scrape(self, client_company_id: uuid.UUID) -> SourcingRunResult:
        """Team-/Mitarbeiter-Seiten der Kanzlei-Website per LLM extrahieren
        (siehe kanzlei_team_scrape.py) und Treffer als Leads anlegen -
        matched_client_company_id ist gesetzt, da von der Kanzlei aus
        gestartet wird."""
        result = SourcingRunResult()
        client = self.session.get(ClientCompany, client_company_id)
        if client is None:
            result.errors.append(f"{client_company_id}: Kunde nicht gefunden")
            return result
        if not client.website:
            result.errors.append(f"{client.name}: keine Website hinterlegt")
            return result
        base_url = client.website
        if not base_url.startswith(("http://", "https://")):
            base_url = f"https://{base_url}"
        try:
            homepage = kanzlei_team_scrape.fetch_page(base_url)
        except httpx.HTTPError as exception:
            result.errors.append(f"{client.name}: Website nicht erreichbar ({exception})")
            return result
        for page_url in kanzlei_team_scrape.find_team_page_urls(base_url, homepage):
            time.sleep(TEAM_PAGE_FETCH_PAUSE_SECONDS)
            try:
                page_html = kanzlei_team_scrape.fetch_page(page_url)
            except httpx.HTTPError:
                # Fallback-Pfade duerfen 404 sein - kein Fehler, naechste URL.
                continue
            page_text = kanzlei_team_scrape.html_to_text(page_html)
            if not page_text:
                continue
            try:
                members = kanzlei_team_scrape.extract_team_members(page_text)
            except (AIProviderError, ValueError) as exception:
                result.errors.append(f"{client.name}: Extraktion fehlgeschlagen ({exception})")
                continue
            result.found += len(members)
            for member in members:
                self._record_lead_result(
                    result,
                    SourcingLeadCreate(
                        source_type=SourcingSourceType.KANZLEI_TEAM_PAGE,
                        source_url=page_url,
                        first_name=member.first_name,
                        last_name=member.last_name,
                        current_employer=client.name,
                        city=client.city,
                        postal_code=client.postal_code,
                        matched_client_company_id=client.id,
                        raw_data={"title": member.title, "team_page": page_url},
                        notes_text=_team_page_notes_text(member),
                    ),
                )
            if result.found > 0:
                # Erste Seite mit echten Treffern reicht - weitere Seiten
                # derselben Kanzlei listen fast immer dieselben Personen.
                break
        return result

    def run_team_scrapes(self, client_company_ids: list[uuid.UUID]) -> SourcingRunResult:
        total = SourcingRunResult()
        for index, company_id in enumerate(client_company_ids):
            if index > 0:
                time.sleep(DIRECTORY_REQUEST_PAUSE_SECONDS)
            _merge_results(total, self.run_kanzlei_team_scrape(company_id))
        return total

    def _resolve_center(self, center: str) -> tuple[float, float]:
        lat, lng, precise = resolve_place_query(self.session, center)
        # Nur ueber den groben PLZ-Zonen-Fallback aufloesbar zaehlt wie "gar
        # nicht" (kann 100+ km danebenliegen, siehe geo.py).
        if lat is None or lng is None or not precise:
            raise BusinessRuleError(f"'{center}' ist als Umkreis-Zentrum nicht auflösbar.")
        return lat, lng

    def postal_codes_around(self, center: str, radius_km: int) -> list[str]:
        lat, lng = self._resolve_center(center)
        postal_codes = postal_codes_within_radius(
            load_postal_locality_index(self.session), lat, lng, radius_km
        )
        if not postal_codes:
            raise BusinessRuleError(f"Keine PLZ im Umkreis von {radius_km} km um '{center}'.")
        return postal_codes

    def company_ids_around(self, center: str, radius_km: int) -> list[uuid.UUID]:
        """Kanzleien mit Website im Umkreis, naechste zuerst. Kanzleien ohne
        praezise aufloesbare PLZ/Ort fallen raus (gleiche Regel wie
        clients.py::list_near_candidate)."""
        lat, lng = self._resolve_center(center)
        index = load_postal_locality_index(self.session)
        companies = self.session.scalars(
            select(ClientCompany).where(
                ClientCompany.website.isnot(None), ClientCompany.website != ""
            )
        ).all()
        in_radius: list[tuple[float, uuid.UUID]] = []
        for company in companies:
            company_lat, company_lng, precise = candidate_coordinates(
                self.session,
                company.city,
                company.postal_code,
                str(company.id),
                apply_jitter=False,
                index=index,
            )
            if company_lat is None or company_lng is None or not precise:
                continue
            distance = haversine_km(lat, lng, company_lat, company_lng)
            if distance <= radius_km:
                in_radius.append((distance, company.id))
        if not in_radius:
            raise BusinessRuleError(
                f"Kein Kunde mit Website im Umkreis von {radius_km} km um '{center}'."
            )
        return [company_id for _, company_id in sorted(in_radius)]

    def _record_lead_result(self, result: SourcingRunResult, payload: SourcingLeadCreate) -> None:
        lead = self.create_lead(payload)
        if lead is None:
            result.skipped_existing += 1
            return
        result.created += 1
        if lead.status == SourcingLeadStatus.POSSIBLE_DUPLICATE:
            result.possible_duplicates += 1

    def approve_lead(self, lead_id: uuid.UUID, user_id: uuid.UUID) -> SourcingLead:
        """Erstellt aus dem Lead einen echten Kandidaten ueber den bestehenden
        CandidateService.create() (gleiche Validierung/Nummernvergabe wie beim
        regulaeren Anlegen - bewusst wiederverwendet statt dupliziert)."""
        lead = self.get_lead(lead_id)
        self._ensure_reviewable(lead)
        # Zusaetzlich zum bisherigen Freitext (notes_text unten) so viel wie
        # moeglich strukturiert uebernehmen (Nutzer-Vorgabe) - current_employer
        # 1:1, job_title/rollen aus raw_data abgeleitet (Feldname je Quelle
        # unterschiedlich), Telefon nur falls die Quelle es liefert.
        job_title = _job_title_from_raw_data(lead.raw_data)
        candidate = CandidateService(self.session).create(
            CandidateCreate(
                first_name=lead.first_name,
                last_name=lead.last_name,
                city=lead.city,
                postal_code=lead.postal_code,
                summary=self._source_summary(lead),
                owner_user_id=user_id,
                current_employer_internal=lead.current_employer,
                job_title=job_title,
                rollen=_rollen_from_text(job_title),
                phone=_phone_from_raw_data(lead.raw_data),
            )
        )
        if lead.notes_text:
            # Freitext ueber die Person (Stellenbeschreibung/Werdegang/weitere
            # online gefundene Infos laut Quelle) landet als Note am neuen
            # Kandidaten - damit bleibt nach der Uebernahme nachvollziehbar,
            # was die Person macht/gemacht hat (Nutzer-Vorgabe).
            NoteService(self.session).create(
                NoteCreate(candidate_id=candidate.id, body=lead.notes_text),
                created_by_user_id=user_id,
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
        return normalized in self._lead_name_index(source_type)

    def _lead_name_index(self, source_type: SourcingSourceType) -> set[str]:
        """Normalisierte Namen aller bereits vorhandenen Leads einer Quelle -
        pro Service-Instanz einmal geladen und bei create_lead fortgeschrieben
        (ein Sourcing-Lauf prueft sonst pro Treffer den kompletten
        Lead-Bestand erneut)."""
        if source_type not in self._lead_names:
            rows = self.session.execute(
                select(SourcingLead.first_name, SourcingLead.last_name).where(
                    SourcingLead.source_type == source_type
                )
            ).all()
            self._lead_names[source_type] = {normalize_person_name(row[0], row[1]) for row in rows}
        return self._lead_names[source_type]

    def _find_similar_candidate(self, first_name: str, last_name: str) -> uuid.UUID | None:
        normalized = normalize_person_name(first_name, last_name)
        if not normalized:
            return None
        best_id: uuid.UUID | None = None
        best_score = 0.0
        # Gestufter Vergleich (real_quick_ratio/quick_ratio als billige obere
        # Schranken vor dem teuren ratio()) - ein Sourcing-Lauf vergleicht
        # sonst hunderte Leads gegen zehntausende Kandidaten mit vollem
        # SequenceMatcher und wird minutenlang.
        matcher = SequenceMatcher()
        matcher.set_seq2(normalized)
        for candidate_id, candidate_name in self._candidate_name_index():
            if candidate_name == normalized:
                return candidate_id
            matcher.set_seq1(candidate_name)
            if matcher.real_quick_ratio() < NAME_SIMILARITY_THRESHOLD:
                continue
            if matcher.quick_ratio() < NAME_SIMILARITY_THRESHOLD:
                continue
            score = matcher.ratio()
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

    def _match_client_company(self, employer: str | None) -> ClientCompany | None:
        """Ordnet den laut Quelle genannten Arbeitgeber-Freitext einer im CRM
        bereits erfassten Kanzlei zu (Fuzzy-Namensvergleich, gleiche Logik/
        Schwelle wie beim Kanzlei-Import, siehe services/name_matching.py).
        Bei Treffer gilt die CRM-Adresse der Kanzlei als verlaesslicher als
        die aus dem Quell-Freitext geparste (siehe Aufrufer)."""
        if not employer:
            return None
        normalized = normalize_company_name(employer)
        if not normalized:
            return None
        best_id: uuid.UUID | None = None
        best_score = 0.0
        for company_id, company_name in self._client_company_name_index():
            score = name_similarity(normalized, company_name)
            if score >= SIMILARITY_THRESHOLD and score > best_score:
                best_id = company_id
                best_score = score
        return self.session.get(ClientCompany, best_id) if best_id is not None else None

    def _client_company_name_index(self) -> list[tuple[uuid.UUID, str]]:
        if self._client_company_names is None:
            rows = self.session.execute(select(ClientCompany.id, ClientCompany.name)).all()
            self._client_company_names = [
                (row[0], normalize_company_name(row[1])) for row in rows
            ]
        return self._client_company_names
