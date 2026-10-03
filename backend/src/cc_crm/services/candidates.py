import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from cc_crm.core.config import get_settings
from cc_crm.core.errors import BusinessRuleError, ConsentNotGrantedError
from cc_crm.core.time import naive_utc
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.contact_person import ContactPerson
from cc_crm.models.enums import Abschlussart, CandidateStatus, ClientStatus, Rolle
from cc_crm.models.note import Note
from cc_crm.models.recruiting import AuditLog, SubmissionFeedback
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.user import User
from cc_crm.repositories.candidates import CandidateRepository
from cc_crm.repositories.notes import NoteRepository
from cc_crm.repositories.operational import DocumentRepository
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.schemas.candidate import CandidateCreate, CandidateUpdate, CvExtractionSuggestion
from cc_crm.schemas.note import CandidateCommentRead
from cc_crm.services.audit_diff import changed_values
from cc_crm.services.base import CrudService
from cc_crm.services.clients import ClientCompanyService
from cc_crm.services.cv_extraction import (
    CV_STRUCTURED_FIELDS,
    derive_rollen_from_text,
    extract_candidate_fields,
    is_agency_letterhead,
)
from cc_crm.services.geo import (
    candidate_coordinates,
    haversine_km,
    load_postal_locality_index,
    resolve_place_query,
)
from cc_crm.services.notes import user_labels, user_labels_by_email
from cc_crm.services.profile_docx_export import persist_anonymous_profile_document
from cc_crm.services.storage import delete_document_bytes

logger = logging.getLogger("cc_crm.candidates")

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
REDACTED = "[entfernt]"  # Ersatzwert fuer geschwaerzte Audit-Werte

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
    custom_field_entity = "candidate"

    def __init__(self, session: Session) -> None:
        repository = CandidateRepository(session)
        super().__init__(session, repository, "Candidate")
        self.candidates = repository
        self.audit_logs = AuditLogRepository(session)
        self.documents = DocumentRepository(session)
        self.notes = NoteRepository(session)

    def _maybe_derive_rollen(self, candidate: Candidate) -> None:
        """Regelbasierte Rollen-Ableitung (kein LLM-Call, siehe
        cv_extraction.py::derive_rollen_from_text) - greift NUR, wenn rollen
        aktuell leer ist (Nutzer-Vorgabe: "nur ergaenzen, nie ueberschreiben"
        - eine bereits gesetzte, ggf. manuell geprueft Rolle bleibt in JEDEM
        Fall unangetastet, auch wenn job_title/qualification sich spaeter
        aendern). Committet selbst, da beide Aufrufstellen (create/update)
        den eigentlichen Schreibvorgang bereits abgeschlossen haben."""
        if candidate.rollen:
            return
        derived = derive_rollen_from_text(candidate.job_title, candidate.qualification)
        if not derived:
            return
        candidate.rollen = derived  # type: ignore[assignment]
        self.session.commit()

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

    def history(self, entity_id: uuid.UUID) -> list[AuditLog]:
        """Aenderungshistorie fuers Kandidatenprofil (Nutzer-Feedback
        "Änderungshistorie im Kandidatenprofil sichtbar machen") - deckt
        Aktionen am Kandidaten selbst UND an all seinen Prozessen ab (siehe
        repositories/recruiting.py::AuditLogRepository.list_for_candidate),
        da die meisten Eintraege (Stufenwechsel) an der jeweiligen
        CandidateSubmission haengen, nicht am Kandidaten."""
        self.get(entity_id)
        submission_ids = list(
            self.session.scalars(
                select(CandidateSubmission.id).where(
                    CandidateSubmission.candidate_id == entity_id
                )
            ).all()
        )
        return list(self.audit_logs.list_for_candidate(entity_id, submission_ids))

    def comments(self, entity_id: uuid.UUID) -> list[CandidateCommentRead]:
        """Alle Notizen (allgemeine UND prozessgebundene) und alle Prozess-
        Feedbacks zu einem Kandidaten, mit Autor - Basis der Kandidaten-
        Timeline. Bewusst ueber ALLE Prozesse des Kandidaten, unabhaengig vom
        Prozess-Owner: Kommentare sind gemeinsames Agenturwissen (Nutzer-
        Vorgabe "jeder Kommentar soll bei jedem angezeigt werden"), die
        Sichtbarkeitsgrenze gilt fuer Prozesse, nicht fuer die Kommentare
        daran. Neueste zuerst."""
        self.get(entity_id)
        submission_ids = list(
            self.session.scalars(
                select(CandidateSubmission.id).where(
                    CandidateSubmission.candidate_id == entity_id
                )
            ).all()
        )
        note_filter = Note.candidate_id == entity_id
        if submission_ids:
            note_filter = or_(note_filter, Note.candidate_submission_id.in_(submission_ids))
        notes = list(self.session.scalars(select(Note).where(note_filter)).all())
        feedback = (
            list(
                self.session.scalars(
                    select(SubmissionFeedback).where(
                        SubmissionFeedback.submission_id.in_(submission_ids)
                    )
                ).all()
            )
            if submission_ids
            else []
        )
        note_authors = user_labels(self.session, (note.created_by_user_id for note in notes))
        feedback_authors = user_labels_by_email(
            self.session, (item.created_by for item in feedback)
        )
        entries = [
            CandidateCommentRead(
                kind="note",
                id=note.id,
                occurred_at=note.created_at,
                author=note_authors.get(note.created_by_user_id)
                if note.created_by_user_id
                else None,
                text=note.body,
                submission_id=note.candidate_submission_id,
            )
            for note in notes
        ] + [
            CandidateCommentRead(
                kind="feedback",
                id=item.id,
                occurred_at=item.received_at,
                # Alt-Eintraege koennen einen frei getippten Namen statt einer
                # E-Mail tragen - dann unveraendert anzeigen.
                author=(
                    feedback_authors.get(item.created_by.lower(), item.created_by)
                    if item.created_by
                    else None
                ),
                text=item.feedback_text,
                stage=item.stage.value if item.stage else None,
                feedback_type=item.feedback_type.value,
                submission_id=item.submission_id,
            )
            for item in feedback
        ]
        entries.sort(key=lambda entry: naive_utc(entry.occurred_at), reverse=True)
        return entries

    def confirm_rollen(self, entity_id: uuid.UUID, current_user: User) -> Candidate:
        """"Bestätigen"-Aktion (Titelschutz-Korrektur Schritt 2): der Nutzer
        hat den Titel geprueft (z.B. im Original-CV nachgesehen) und
        bestaetigt ihn als korrekt, OHNE rollen selbst zu aendern - reines
        Loeschen des Flags. Fuer die Gegenaktion ("Rolle korrigieren", bei
        der rollen sich tatsaechlich aendert) siehe update() oben; die gibt
        es bewusst nicht als eigene Methode, weil sie einfach die normale
        Rollen-Bearbeitung ist."""
        candidate = self.get(entity_id)
        if not candidate.rollen_unbestaetigt:
            return candidate
        candidate.rollen_unbestaetigt = False
        self.audit_logs.create(
            {
                "entity_type": "candidate",
                "entity_id": candidate.id,
                "action": "rollen_bestaetigt",
                "changed_by": current_user.email,
                "old_values": {"rollen_unbestaetigt": True},
                "new_values": {"rollen_unbestaetigt": False, "rollen": list(candidate.rollen)},
            }
        )
        self.session.commit()
        self.session.refresh(candidate)
        return candidate

    def update(
        self,
        entity_id: uuid.UUID,
        payload: CandidateUpdate,
        current_user: User | None = None,
    ) -> Candidate:
        """Stempelt cv_in_recorded_at, sobald cv_available echt (neu) auf
        True wechselt - einmalig, nie erneut ueberschrieben. Getrennt vom
        reinen Anzeige-Flag cv_available, damit Analytics ("CV In") nur
        echte, ab dem Stichtag neu erfasste CV-Ins zaehlt statt der 2481
        beim Datenuebertrag pauschal gesetzten Alt-Kandidaten (siehe
        Modul-Docstring in models/candidate.py, Nutzer-Feedback 2026-07-15).

        Titelschutz-Korrektur Schritt 2: loescht rollen_unbestaetigt
        automatisch, sobald rollen sich durch dieses Update tatsaechlich
        AENDERT - das ist die "Rolle korrigieren"-Aktion (oeffnet im
        Frontend einfach die normale Rollen-Bearbeitung, siehe Auftrag,
        statt einen eigenen Dialog zu brauchen). Bewusst ein Wertevergleich
        statt "rollen war im Payload gesetzt": das Bearbeiten-Formular
        schickt rollen bei JEDER Aenderung mit (auch wenn nur z.B. das
        Gehalt geaendert wurde) - ohne den Wertevergleich wuerde das Flag
        schon bei einer voellig unrelated Aenderung geloescht. Schreibt
        einen AuditLog-Eintrag, damit die Korrektur in der Aenderungs-
        historie auftaucht (current_user optional fuer Rueckwaertskompatibi-
        litaet zu bestehenden Aufrufstellen ohne current_user, changed_by
        bleibt dann None wie bei anderen automatischen Eintraegen)."""
        before = self.get(entity_id)
        was_cv_available = before.cv_available
        was_rollen_unbestaetigt = before.rollen_unbestaetigt
        old_rollen = list(before.rollen)
        old_values, new_values = changed_values(before, payload.model_dump(exclude_unset=True))

        updated = super().update(entity_id, payload)
        if new_values:
            self.audit_logs.create(
                {
                    "entity_type": "candidate",
                    "entity_id": updated.id,
                    "action": "updated",
                    "changed_by": current_user.email if current_user else None,
                    "old_values": old_values,
                    "new_values": new_values,
                }
            )
            self.session.commit()
        if updated.cv_available and not was_cv_available and updated.cv_in_recorded_at is None:
            updated.cv_in_recorded_at = datetime.now(UTC)
            self.session.commit()
        if was_rollen_unbestaetigt and list(updated.rollen) != old_rollen:
            updated.rollen_unbestaetigt = False
            self.audit_logs.create(
                {
                    "entity_type": "candidate",
                    "entity_id": updated.id,
                    "action": "rollen_korrigiert",
                    "changed_by": current_user.email if current_user else None,
                    "old_values": {"rollen": old_rollen, "rollen_unbestaetigt": True},
                    "new_values": {
                        "rollen": list(updated.rollen),
                        "rollen_unbestaetigt": False,
                    },
                }
            )
            self.session.commit()
        # Zwischenthema "Rolle fehlt bei gefuelltem Jobtitel": nur wenn
        # job_title/qualification tatsaechlich Teil dieses Updates waren -
        # sonst wuerde JEDES unrelated Update (z.B. Gehalt) versuchen, eine
        # laengst leer gelassene Rolle nachzutragen, obwohl sich am Jobtitel
        # gar nichts geaendert hat. _maybe_derive_rollen greift ohnehin nur,
        # wenn rollen aktuell leer ist (nie ueberschreiben).
        if "job_title" in payload.model_fields_set or "qualification" in payload.model_fields_set:
            self._maybe_derive_rollen(updated)
        if "short_profile" in payload.model_fields_set and updated.short_profile:
            # Legt das gerade (neu) gespeicherte anonyme Profil automatisch
            # als "Nr. XXXX.docx"-Dokument ab (Auftrag "Schnelle Submission",
            # Punkt "Anonymes Profil wird nicht dauerhaft abgelegt"). Ein
            # Fehler hierbei (z.B. ein noch nicht parsebarer Profiltext)
            # darf das eigentliche Speichern von short_profile NICHT
            # verhindern - best effort, wie die Sent-Ordner-Ablage bei
            # services/mail_send.py.
            try:
                persist_anonymous_profile_document(self.session, updated)
            except Exception:  # noqa: BLE001 - Dokumenten-Ablage ist best effort
                logger.warning(
                    "Anonymes Profil konnte nicht als Dokument abgelegt werden (Kandidat %s)",
                    updated.id,
                    exc_info=True,
                )
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
        candidate.custom_fields = {}  # Zusatzfelder koennen Personenbezug haben
        for field in _ANONYMIZE_TEXT_FIELDS:
            setattr(candidate, field, None)

        self._redact_audit_history(candidate.id)

        # Bewusst KEINE personenbezogenen Werte (Name, E-Mail, ...) ins
        # Audit-Log schreiben - alter_values wuerde sonst genau die Daten
        # reproduzieren, die diese Aktion gerade entfernt.
        self.audit_logs.create(
            {
                "entity_type": "candidate",
                "entity_id": candidate.id,
                "action": "anonymized",
                "changed_by": admin_user.email,
                "new_values": {
                    "fields_cleared": [*_ANONYMIZE_TEXT_FIELDS, "no_gos", "custom_fields"]
                },
            }
        )
        self.session.commit()
        self.session.refresh(candidate)
        return candidate

    def _redact_audit_history(self, candidate_id: uuid.UUID) -> None:
        """Schwaerzt die alten/neuen Werte frueherer Audit-Eintraege dieses
        Kandidaten (E-Mail, Telefon, Name ... aus normalen Aenderungen). Die
        Eintraege selbst bleiben (wer/wann/welche Aktion/welche Felder);
        nur die WERTE werden durch "[entfernt]" ersetzt. Der Audit-Log ist
        per Datenbank-Trigger sonst unveraenderbar (Migration f4b7d1a8c2e5) -
        diese Funktion setzt dafuer das transaktionsgebundene Flag."""
        if self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(text("SET LOCAL cc_crm.audit_redaction = 'on'"))
        rows = self.session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "candidate", AuditLog.entity_id == candidate_id
            )
        ).all()
        for row in rows:
            for column in ("old_values", "new_values"):
                values = getattr(row, column)
                if isinstance(values, dict) and values:
                    setattr(row, column, {key: REDACTED for key in values})
        self.session.flush()

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

    def _parse_custom_field_filter(self, raw: str | None) -> tuple[str, str, str] | None:
        """"schluessel:wert" -> (Schluessel, Feldtyp, Wert); Feld muss definiert sein."""
        if not raw:
            return None
        key, separator, value = raw.partition(":")
        if not separator or not key:
            raise BusinessRuleError("Eigener Feld-Filter erwartet 'schluessel:wert'.")
        from cc_crm.services.custom_fields import CustomFieldService

        kind = CustomFieldService(self.session).filter_kind("candidate", key)
        if kind == "number":
            try:
                float(value)
            except ValueError as exc:
                raise BusinessRuleError("Zahlenfeld-Filter erwartet eine Zahl.") from exc
        return key, kind, value

    def list_filtered(
        self,
        *,
        status: CandidateStatus | None = None,
        role: str | None = None,
        rollen: list[Rolle] | None = None,
        abschluesse: list[Abschlussart] | None = None,
        region: str | None = None,
        search: str | None = None,
        plz_ort: str | None = None,
        radius_km: int | None = None,
        owner_user_id: uuid.UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        rollen_unbestaetigt: bool | None = None,
        custom_field: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "asc",
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[Candidate], int]:
        custom_field_filter = self._parse_custom_field_filter(custom_field)
        # plz_ort+radius_km ist ein ECHTER Umkreis-Filter (siehe
        # MAX_RADIUS_FILTER_CANDIDATES oben) - beide muessen gesetzt sein,
        # sonst gaebe es kein Zentrum bzw. keinen Radius zum Filtern.
        if plz_ort and radius_km:
            return self._list_filtered_by_radius(
                status=status,
                role=role,
                rollen=rollen,
                abschluesse=abschluesse,
                region=region,
                search=search,
                plz_ort=plz_ort,
                radius_km=radius_km,
                owner_user_id=owner_user_id,
                created_from=created_from,
                created_to=created_to,
                rollen_unbestaetigt=rollen_unbestaetigt,
                custom_field_filter=custom_field_filter,
                sort_by=sort_by,
                sort_dir=sort_dir,
                offset=offset,
                limit=limit,
            )

        entities, total = self.candidates.filtered(
            status=status,
            role=role,
            rollen=rollen,
            abschluesse=abschluesse,
            region=region,
            search=search,
            owner_user_id=owner_user_id,
            created_from=created_from,
            created_to=created_to,
            rollen_unbestaetigt=rollen_unbestaetigt,
            custom_field_filter=custom_field_filter,
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
        abschluesse: list[Abschlussart] | None,
        region: str | None,
        search: str | None,
        plz_ort: str,
        radius_km: int,
        owner_user_id: uuid.UUID | None,
        created_from: datetime | None,
        created_to: datetime | None,
        rollen_unbestaetigt: bool | None = None,
        custom_field_filter: tuple[str, str, str] | None = None,
        sort_by: str | None,
        sort_dir: str,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Candidate], int]:
        center_lat, center_lng, center_precise = resolve_place_query(self.session, plz_ort)
        if center_lat is None or center_lng is None or not center_precise:
            # Zentrum nicht aufloesbar ODER nur ueber die grobe PLZ_ZONE_
            # COORDINATES-Naeherung aufloesbar (siehe geo.py::
            # resolve_place_query-Docstring - die Zonen-Naeherung kann 100+ km
            # danebenliegen, ist fuer einen harten Radius-Filter also genauso
            # ungeeignet wie "gar nicht aufloesbar") - 0 Treffer statt den
            # Filter stillschweigend zu ignorieren, sonst wirkt er kaputt
            # (Nutzer-Vorgabe) bzw. taeuscht ungefilterte oder faelschlich
            # irrefuehrende Ergebnisse vor.
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
            abschluesse=abschluesse,
            region=region,
            search=search,
            owner_user_id=owner_user_id,
            created_from=created_from,
            created_to=created_to,
            rollen_unbestaetigt=rollen_unbestaetigt,
            custom_field_filter=custom_field_filter,
            sort_by=sort_by,
            sort_dir=sort_dir,
            offset=0,
            limit=MAX_RADIUS_FILTER_CANDIDATES,
        )

        # EINMAL fuer den gesamten Radius-Filter geladen statt pro Kandidat
        # eine eigene DB-Query (N+1-Query-Problem, siehe geo.py::
        # PostalLocalityIndex-Docstring - fiel erst auf, seit postal_
        # localities in Produktion befuellt ist und diese Schleife
        # ueberhaupt erreicht wird; bei ~2.900 Kandidaten waren das bis zu
        # ~5.800 sequenzielle Roundtrips, der Request timete aus).
        index = load_postal_locality_index(self.session)

        in_radius: list[Candidate] = []
        for candidate in candidates:
            # apply_jitter=False: eine Distanzberechnung fuer einen harten
            # Radius-Filter darf nicht vom deterministischen Karten-Versatz
            # (bis zu ~0.06 Grad ≈ 5-7km) beeinflusst werden, sonst koennte
            # derselbe Kandidat bei einem knappen Radius inkonsistent rein-/
            # rausfallen (siehe geo.py::candidate_coordinates-Docstring).
            cand_lat, cand_lng, cand_precise = candidate_coordinates(
                self.session,
                candidate.city,
                candidate.postal_code,
                str(candidate.id),
                apply_jitter=False,
                index=index,
            )
            if cand_lat is None or cand_lng is None or not cand_precise:
                # Kandidat ohne aufloesbare ODER nur ueber die grobe Zonen-
                # Naeherung aufloesbare Koordinaten faellt bei einem AKTIVEN
                # Radius-Filter raus (anders als beim Vakanzen-Matching, wo
                # das nur ein Bonus-Kriterium ist und unaufloesbare
                # Kandidaten regulaer mitgezaehlt werden - hier ist es ein
                # expliziter Filter, sonst wirkt er kaputt bzw. liefert
                # strukturell falsche Treffer wie beim Illingen/Saar-Vorfall).
                continue
            if haversine_km(center_lat, center_lng, cand_lat, cand_lng) <= radius_km:
                in_radius.append(candidate)

        total = len(in_radius)
        page = list(in_radius[offset : offset + limit])
        self._attach_ghosting_flags(page)
        return page, total

    def cv_out_targets(
        self, entity_id: uuid.UUID, *, radius_km: int
    ) -> list[tuple[ClientCompany, float, list[ContactPerson]]]:
        """CV-Out-Kampagne (Auftrag '"CV Out"-Kampagne am Kandidaten'):
        Kanzleien im Umkreis des Kandidaten, die fuer einen Mailing-Versand
        infrage kommen - reine Lesefunktion, legt noch keine MailingGroup an
        (das macht das Frontend erst nach Bestaetigung der Auswahl per
        POST /mailing-groups, gleiches Muster wie geo-results-table.tsx::
        createGroupFromSelection).

        Wiederverwendet list_near_candidate() aus services/clients.py
        (gleiches Zentrum, gleiche Distanzberechnung, keine neue Geo-Logik),
        filtert das Ergebnis danach:
        - Kanzleien mit Status BLOCKED ("Gesperrt", rot) fallen raus -
          Nutzer-Vorgabe, nie kontaktieren.
        - Kanzleien ohne mindestens einen Kontakt mit E-Mail-Adresse fallen
          raus (ohne E-Mail waere dort ohnehin niemand mailingfaehig).
        Pro verbleibender Kanzlei werden NUR die Kontakte MIT E-Mail-Adresse
        zurueckgegeben (Auftrag: "Liste mit vorausgewaehlten Kontaktpersonen,
        nur mit E-Mail"), Hauptkontakt (is_primary) zuerst.

        Consent-Check (candidate.consent_received) greift hier VOR der
        Umkreissuche: services/mail_send.py::_ensure_consent prueft
        candidate.consent_received nur, wenn ein candidate_id im
        Versand-Kontext mitgegeben wird - beim CV-Out-Mailing sind die
        Empfaenger aber Kanzlei-Kontakte (kind="contact"), nicht der
        Kandidat selbst, daher greift dieser bestehende Check beim
        eigentlichen Bulk-Versand NICHT automatisch. Damit die
        Consent-Vorgabe trotzdem unveraendert aktiv bleibt (Auftrag:
        "Consent-Check bleibt unveraendert aktiv"), wird sie hier am
        eigentlichen Einstiegspunkt der Kampagne erzwungen: ohne
        Einwilligung wird die Kampagne gar nicht erst angeboten."""
        candidate = self.get(entity_id)
        if not candidate.consent_received:
            raise ConsentNotGrantedError(
                "Kein Einverständnis des Kandidaten zur Weitergabe erfasst "
                f"(Kandidat: {candidate.first_name} {candidate.last_name})."
            )

        in_radius, _unresolved = ClientCompanyService(self.session).list_near_candidate(
            entity_id, radius_km=radius_km
        )

        targets: list[tuple[ClientCompany, float, list[ContactPerson]]] = []
        for client, distance in in_radius:
            if client.status == ClientStatus.BLOCKED:
                continue
            contacts = list(
                self.session.scalars(
                    select(ContactPerson)
                    .where(
                        ContactPerson.client_company_id == client.id,
                        ContactPerson.email.is_not(None),
                    )
                    .order_by(ContactPerson.is_primary.desc(), ContactPerson.last_name)
                ).all()
            )
            if not contacts:
                continue
            targets.append((client, distance, contacts))

        return targets

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
        """Vergibt bei Bedarf candidate_number, UND leitet rollen regel-
        basiert aus job_title/qualification ab, wenn beim Anlegen keine
        Rolle mitgegeben wurde (Zwischenthema "Rolle fehlt bei gefuelltem
        Jobtitel" - manuelles Anlegen und die Sourcing-Uebernahme liefern
        job_title, aber bisher NICHTS leitete rollen daraus ab, anders als
        beim CV-Upload). Ergaenzt NUR, ueberschreibt NIE - greift
        ausschliesslich, wenn rollen nach dem Erstellen noch leer ist
        (siehe _maybe_derive_rollen).

        Stempelt AUSSERDEM cv_in_recorded_at, wenn der Kandidat direkt MIT
        cv_available=True angelegt wird (Bugfix "CV In-Analytics zaehlt
        frisch angelegte Kandidaten mit CV nicht mit", konkreter Fall:
        Lorenz Hafner). update() unten stempelt das Feld schon seit laengerem
        beim False->True-Uebergang waehrend einer Bearbeitung - ein direkt
        MIT gesetztem cv_available angelegter Kandidat durchlaeuft diesen
        Uebergang aber nie (es gibt kein "vorher"), cv_in_recorded_at blieb
        bisher faelschlich fuer immer NULL, obwohl der CV nachweislich
        brandneu ist. Bewusst OHNE die was_cv_available-Vorher-Pruefung aus
        update(): bei der Anlage gibt es kein "vorher", jeder mit gesetztem
        CV-Flag angelegte Kandidat soll gezaehlt werden - siehe auch den
        Backfill in scripts/backfill_cv_in_recorded_at.py fuer bereits vor
        diesem Fix betroffene Kandidaten."""
        if not payload.candidate_number:
            payload = payload.model_copy(update={"candidate_number": self._next_candidate_number()})
        entity = super().create(payload)
        self._maybe_derive_rollen(entity)
        if entity.cv_available and entity.cv_in_recorded_at is None:
            entity.cv_in_recorded_at = datetime.now(UTC)
            self.session.commit()
        return entity


def _months_ago(months: int) -> date:
    today = datetime.now(UTC).date()
    return today - timedelta(days=months * 30)
