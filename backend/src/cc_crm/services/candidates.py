import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.config import get_settings
from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import CandidateStatus, Rolle
from cc_crm.models.user import User
from cc_crm.repositories.candidates import CandidateRepository
from cc_crm.repositories.notes import NoteRepository
from cc_crm.repositories.operational import DocumentRepository
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.schemas.candidate import CandidateCreate, CandidateUpdate, CvExtractionSuggestion
from cc_crm.services.base import CrudService
from cc_crm.services.cv_extraction import (
    CV_STRUCTURED_FIELDS,
    extract_candidate_fields,
    is_agency_letterhead,
)
from cc_crm.services.geo import candidate_coordinates, haversine_km, resolve_place_query
from cc_crm.services.storage import delete_document_bytes

# Obergrenze fuer den PLZ+Umkreis-Filter (list_filtered mit plz_ort+radius_km):
# Umkreis-Distanz ist auf den bestehenden Spalten (kein gespeichertes lat/lng)
# nicht per SQL-WHERE berechenbar, deshalb gleiches Pragma wie
# VacancyMatchingService.find_matches - bis zu 5000 nach den UEBRIGEN Filtern
# (status/rollen/search/owner/...) bereits eingeschraenkte Kandidaten laden
# und serverseitig in Python per haversine_km auf den Radius einschraenken,
# ERST DANACH paginieren. Der Normalfall OHNE Radius-Filter bleibt komplett
# unberuehrt (weiterhin echtes SQL OFFSET/LIMIT, keine Verlangsamung).
MAX_RADIUS_FILTER_CANDIDATES = 5000

# Gleiche Struktur wie QUALI_CALL_NOTE_TEMPLATE im Frontend (notes-panel.tsx)
# - bewusst identisch gehalten, damit eine automatisch aus dem CV erstellte
# Profilzusammenfassung und eine manuell waehrend eines Quali-Calls
# eingefuegte Notiz gleich aussehen. Gehalt/Kuendigungsfrist/Wechselmotivation
# stehen nie in einem CV - bleiben hier absichtlich leer, fuer den
# spaeteren Quali-Call.
_PROFILE_SUMMARY_NOTE_TEMPLATE = (
    "Profilzusammenfassung aus CV (automatisch erstellt):\n\n"
    "Ort: {city}\n"
    "Ausbildung: {ausbildung_titel}\n"
    "Gehalt: \n"
    "Kündigungsfrist/Verfügbarkeit: \n\n"
    "Erfahrungen: {erfahrungen_zusammenfassung}\n\n"
    "Wechselmotivation: \n\n"
    "EDV: {edv}"
)

# Freitextfelder mit Personenbezug, die bei der Anonymisierung (siehe
# CandidateService.anonymize) auf None/leer gesetzt werden - bewusst NICHT
# die strukturierten/statistischen Felder (job_title, qualification, PLZ/
# Ort, status, fachliche_schwerpunkte, ...), die fuer Auswertungen erhalten
# bleiben sollen (Nutzer-Vorgabe: "Statistiken bleiben auswertbar").
_ANONYMIZE_TEXT_FIELDS = [
    "email",
    "phone",
    "linkedin_url",
    "referred_by",
    "summary",
    "short_profile",
    "freitext_notizen",
    "wechselgrund",
    "next_step",
]

# Letzte reale Kandidatennummer aus der bisherigen (nicht-CRM-) Nummerierung.
# Neue, automatisch vergebene Nummern schließen daran an (ab 4053), damit CRM-
# Kandidaten und die historischen anonymen Profile eine durchgehende Zählung bilden.
_LEGACY_CANDIDATE_NUMBER_FLOOR = 4052


class CandidateService(CrudService[Candidate, CandidateCreate, CandidateUpdate]):
    def __init__(self, session: Session) -> None:
        repository = CandidateRepository(session)
        super().__init__(session, repository, "Candidate")
        self.candidates = repository
        self.audit_logs = AuditLogRepository(session)
        self.documents = DocumentRepository(session)
        self.notes = NoteRepository(session)

    def delete(self, entity_id: uuid.UUID, current_user: User | None = None) -> None:
        # Loeschung ist sicherheits-/nachvollziehbarkeitsrelevant (Punkt 2 des
        # Auftrags) - deshalb vor dem eigentlichen Delete geloggt, unabhaengig
        # vom Erfolg des Deletes selbst waere die Reihenfolge sonst unklar.
        candidate = self.get(entity_id)
        self.audit_logs.create(
            {
                "entity_type": "candidate",
                "entity_id": candidate.id,
                "action": "deleted",
                "changed_by": current_user.email if current_user else None,
                "old_values": {
                    "candidate_number": candidate.candidate_number,
                    "first_name": candidate.first_name,
                    "last_name": candidate.last_name,
                },
            }
        )
        self.session.commit()
        super().delete(entity_id)

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

    def anonymize(self, entity_id: uuid.UUID, admin_user: User) -> Candidate:
        """DSGVO-Vorbereitung (rein technische Grundlage, siehe Punkt 4 des
        Auftrags - keine Rechtsberatung): ersetzt/loescht die
        personenbezogenen Freitextfelder eines Kandidaten sowie seine
        CV-Dokumente, behaelt den Datensatz selbst aber (referenzielle
        Integritaet zu Prozessen/Placements bleibt bestehen, strukturierte
        Felder fuer Statistiken bleiben erhalten). Admin-only (siehe
        API-Layer)."""
        candidate = self.get(entity_id)

        for document in self.documents.filtered(owner_type="candidate", owner_id=candidate.id):
            delete_document_bytes(document.storage_key)
            self.documents.delete(document)

        candidate.first_name = "Anonymisiert"
        candidate.last_name = "Anonymisiert"
        candidate.anrede = None
        candidate.consent_received = False
        candidate.cv_available = False
        candidate.no_gos = []
        for field in _ANONYMIZE_TEXT_FIELDS:
            setattr(candidate, field, None)

        # Bewusst KEINE personenbezogenen Werte (Name, E-Mail, ...) ins
        # Audit-Log schreiben - alter_values wuerde sonst genau die Daten
        # reproduzieren, die diese Aktion gerade entfernt.
        self.audit_logs.create(
            {
                "entity_type": "candidate",
                "entity_id": candidate.id,
                "action": "anonymized",
                "changed_by": admin_user.email,
                "new_values": {"fields_cleared": [*_ANONYMIZE_TEXT_FIELDS, "no_gos"]},
            }
        )
        self.session.commit()
        self.session.refresh(candidate)
        return candidate

    def _extract_and_suggest(
        self,
        candidate: Candidate,
        cv_text: str,
        *,
        filename: str | None,
        content: bytes | None,
    ) -> tuple[dict[str, Any], CvExtractionSuggestion]:
        """Ein einzelner KI-Aufruf pro CV, geteilt zwischen suggest_cv_fields
        (nur Vorschlag) und auto_fill_from_cv (Vorschlag + Persistierung) -
        vermeidet, dieselbe Extraktion zweimal anzustossen. Gibt zusaetzlich
        das komplette Rohergebnis zurueck (siehe Candidate.cv_extraction_raw),
        damit auch nicht als eigene Spalte gefuehrte Felder (z.B.
        erfahrungen_zusammenfassung) nicht verloren gehen."""
        extracted = extract_candidate_fields(cv_text, filename=filename, content=content)

        # CV_STRUCTURED_FIELDS statt Feld-fuer-Feld-Aufzaehlung: die einzige
        # Stelle, die ein neues strukturiertes Feld kennen muss, ist die
        # Registry in cv_extraction.py (siehe Kommentar dort). Python-
        # Truthiness behandelt sowohl None/"" als auch [] als "leer", ein
        # bestehender Wert wird also fuer String- UND Listenfelder nie
        # ueberschrieben.
        suggestions: dict[str, Any] = {}
        for field in CV_STRUCTURED_FIELDS:
            value = extracted.get(field)
            current_value = getattr(candidate, field)
            suggestions[field] = value if (value and not current_value) else None

        suggestion = CvExtractionSuggestion(
            **suggestions, source_is_agency_profile=is_agency_letterhead(cv_text)
        )
        return extracted, suggestion

    def suggest_cv_fields(
        self,
        candidate_id: uuid.UUID,
        cv_text: str,
        *,
        filename: str | None = None,
        content: bytes | None = None,
    ) -> CvExtractionSuggestion:
        """Phase M, Punkt 2: schlaegt aus einem hochgeladenen CV nur Felder
        vor, die beim Kandidaten aktuell leer sind - ein vorhandener Wert
        wird nie ueberschrieben, auch nicht als Vorschlag. filename/content
        optional fuer den Vision-Fallback (siehe extract_candidate_fields)."""
        candidate = self.get(candidate_id)
        _, suggestion = self._extract_and_suggest(
            candidate, cv_text, filename=filename, content=content
        )
        return suggestion

    def preview_cv_extraction(
        self,
        candidate_id: uuid.UUID,
        cv_text: str,
        *,
        filename: str | None = None,
        content: bytes | None = None,
    ) -> tuple[dict[str, Any], CvExtractionSuggestion]:
        """Oeffentliche, rein lesende Variante von suggest_cv_fields, die
        zusaetzlich das Rohergebnis zurueckgibt - genutzt vom Backfill-Skript
        fuer einen praezisen Dry-Run-Bericht (inkl. ob eine Profil-
        zusammenfassungs-Notiz angelegt wuerde, siehe
        would_create_profile_summary_note), ohne dafuer einen zweiten
        KI-Aufruf zu brauchen."""
        candidate = self.get(candidate_id)
        return self._extract_and_suggest(candidate, cv_text, filename=filename, content=content)

    def would_create_profile_summary_note(
        self, candidate_id: uuid.UUID, extracted: dict[str, Any]
    ) -> bool:
        """Rein lesende Vorschau von _profile_summary_note_is_applicable
        (siehe dort) - fuer den Dry-Run-Bericht des Backfill-Skripts."""
        candidate = self.get(candidate_id)
        return self._profile_summary_note_is_applicable(candidate, extracted)

    def auto_fill_from_cv(
        self,
        candidate_id: uuid.UUID,
        cv_text: str,
        *,
        filename: str | None = None,
        content: bytes | None = None,
    ) -> CvExtractionSuggestion:
        """Wendet die aus dem CV erkannten Felder (siehe suggest_cv_fields)
        sofort auf den Kandidaten an, statt eine manuelle Bestaetigung pro
        Feld zu verlangen - Nutzer-Vorgabe: Felder sollen "beim Hochladen
        eines Profils sofort entstehen". Ueberschreibt wie zuvor nie einen
        bereits vorhandenen Wert (suggest_cv_fields liefert dafuer je Feld
        None). Speichert zusaetzlich das komplette Rohergebnis
        (cv_extraction_raw) und legt - einmalig, nur wenn der Kandidat noch
        keine einzige Notiz hat - eine automatische Profilzusammenfassungs-
        Notiz an. Gibt zurueck, was tatsaechlich uebernommen wurde, damit das
        Frontend das dem Nutzer anzeigen kann."""
        candidate = self.get(candidate_id)
        extracted, suggestion = self._extract_and_suggest(
            candidate, cv_text, filename=filename, content=content
        )

        updates = {
            field: getattr(suggestion, field)
            for field in CV_STRUCTURED_FIELDS
            if getattr(suggestion, field)
        }
        for field, value in updates.items():
            setattr(candidate, field, value)
        candidate.cv_extraction_raw = extracted

        self._maybe_create_profile_summary_note(candidate, extracted)

        self.session.commit()
        return suggestion

    def _profile_summary_note_is_applicable(
        self, candidate: Candidate, extracted: dict[str, Any]
    ) -> bool:
        """Bedingung fuer die automatische Profilzusammenfassungs-Notiz
        (Nutzer-Vorgabe: "kann als erste Notiz stehen") - nur wenn (a) der
        Kandidat noch keine einzige Notiz hat (sonst wuerde jeder erneute
        CV-Upload eine weitere Zusammenfassung anhaengen) und (b) die
        Extraktion ueberhaupt etwas Konkretes ergeben hat (sonst waere es nur
        die leere Vorlage ohne Mehrwert gegenueber dem manuellen "Quali-Call-
        Entwurf einfuegen"-Button im Notizen-Tab)."""
        has_content = any(
            [
                extracted.get("city"),
                extracted.get("ausbildung_titel"),
                extracted.get("erfahrungen_zusammenfassung"),
                extracted.get("fachliche_schwerpunkte"),
            ]
        )
        if not has_content:
            return False
        return not self.notes.filtered(candidate_id=candidate.id, limit=1)

    def _maybe_create_profile_summary_note(
        self, candidate: Candidate, extracted: dict[str, Any]
    ) -> None:
        if not self._profile_summary_note_is_applicable(candidate, extracted):
            return

        edv = ", ".join(extracted.get("fachliche_schwerpunkte") or [])
        body = _PROFILE_SUMMARY_NOTE_TEMPLATE.format(
            city=extracted.get("city") or "",
            ausbildung_titel=extracted.get("ausbildung_titel") or "",
            erfahrungen_zusammenfassung=extracted.get("erfahrungen_zusammenfassung") or "",
            edv=edv,
        )
        self.notes.create({"candidate_id": candidate.id, "body": body})

    def list_filtered(
        self,
        *,
        status: CandidateStatus | None = None,
        role: str | None = None,
        rollen: list[Rolle] | None = None,
        region: str | None = None,
        search: str | None = None,
        plz_ort: str | None = None,
        radius_km: int | None = None,
        owner_user_id: uuid.UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        sort_by: str | None = None,
        sort_dir: str = "asc",
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[Candidate], int]:
        # plz_ort+radius_km ist ein ECHTER Umkreis-Filter (siehe
        # MAX_RADIUS_FILTER_CANDIDATES oben) - beide muessen gesetzt sein,
        # sonst gaebe es kein Zentrum bzw. keinen Radius zum Filtern.
        if plz_ort and radius_km:
            return self._list_filtered_by_radius(
                status=status,
                role=role,
                rollen=rollen,
                region=region,
                search=search,
                plz_ort=plz_ort,
                radius_km=radius_km,
                owner_user_id=owner_user_id,
                created_from=created_from,
                created_to=created_to,
                sort_by=sort_by,
                sort_dir=sort_dir,
                offset=offset,
                limit=limit,
            )

        entities, total = self.candidates.filtered(
            status=status,
            role=role,
            rollen=rollen,
            region=region,
            search=search,
            owner_user_id=owner_user_id,
            created_from=created_from,
            created_to=created_to,
            sort_by=sort_by,
            sort_dir=sort_dir,
            offset=offset,
            limit=limit,
        )
        self._attach_ghosting_flags(entities)
        return entities, total

    def _list_filtered_by_radius(
        self,
        *,
        status: CandidateStatus | None,
        role: str | None,
        rollen: list[Rolle] | None,
        region: str | None,
        search: str | None,
        plz_ort: str,
        radius_km: int,
        owner_user_id: uuid.UUID | None,
        created_from: datetime | None,
        created_to: datetime | None,
        sort_by: str | None,
        sort_dir: str,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Candidate], int]:
        center_lat, center_lng = resolve_place_query(plz_ort)
        if center_lat is None or center_lng is None:
            # Zentrum nicht aufloesbar (unbekannter Ort/PLZ) - 0 Treffer statt
            # den Filter stillschweigend zu ignorieren, sonst wirkt er kaputt
            # (Nutzer-Vorgabe) bzw. taeuscht ungefilterte Ergebnisse vor.
            return [], 0

        # Alle UEBRIGEN Filter (status/rollen/search/owner/...) laufen weiter
        # als echtes SQL-WHERE - nur die Radius-Einschraenkung selbst ist
        # Python-seitig, weil dafuer kein gespeichertes lat/lng existiert.
        # order_by(sort_by/sort_dir) laeuft bereits hier per SQL, die
        # anschliessende Python-Filterung entfernt nur einzelne Zeilen aus
        # dieser bereits sortierten Menge, sortiert also NICHT neu.
        candidates, _ = self.candidates.filtered(
            status=status,
            role=role,
            rollen=rollen,
            region=region,
            search=search,
            owner_user_id=owner_user_id,
            created_from=created_from,
            created_to=created_to,
            sort_by=sort_by,
            sort_dir=sort_dir,
            offset=0,
            limit=MAX_RADIUS_FILTER_CANDIDATES,
        )

        in_radius: list[Candidate] = []
        for candidate in candidates:
            cand_lat, cand_lng = candidate_coordinates(
                candidate.city, candidate.postal_code, str(candidate.id)
            )
            if cand_lat is None or cand_lng is None:
                # Kandidat ohne aufloesbare Koordinaten faellt bei einem
                # AKTIVEN Radius-Filter raus (anders als beim Vakanzen-
                # Matching, wo das nur ein Bonus-Kriterium ist und
                # unaufloesbare Kandidaten regulaer mitgezaehlt werden -
                # hier ist es ein expliziter Filter, sonst wirkt er kaputt).
                continue
            if haversine_km(center_lat, center_lng, cand_lat, cand_lng) <= radius_km:
                in_radius.append(candidate)

        total = len(in_radius)
        page = list(in_radius[offset : offset + limit])
        self._attach_ghosting_flags(page)
        return page, total

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
