"""Generates anonymised candidate short-profiles for outbound CV-Outs.

The prompt and rules here are the Commandeur Consulting house style for
candidate profiles sent to Kanzleien - see docs/ for the original spec.

IMPORTANT: `wechselgrund` and `no_gos` are internal-only fields (visible in
the CRM, editable by the consultant) and must NEVER be included in the data
sent to the LLM or in any generated/outgoing document. This is enforced in
`_build_quali_call_payload` below, not just by prompt instruction.

Datenquelle: bis zu diesem Fix stammten ALLE Angaben ausschliesslich aus den
manuell im Quali-Call-Formular gepflegten Candidate-Feldern
(fachliche_schwerpunkte, berufliche_stationen, summary, ...). Fuer die
grosse Mehrheit der Kandidaten, die nur ein hochgeladenes CV-Dokument haben
aber nie durch ein manuelles Quali-Call-Formular liefen, war dieser Payload
praktisch leer - das erzeugte Profil war dann faktisch leer/unbrauchbar
("Anonymes Profil funktioniert nicht", Nutzer-Feedback). Der Generator liest
jetzt zusaetzlich den Text des zuletzt hochgeladenen CV-Dokuments (falls
vorhanden) und gibt ihn dem LLM als zweite Quelle mit - die strukturierten
Quali-Call-Felder bleiben die bevorzugte, von einem Menschen kuratierte
Quelle, der CV-Text schliesst Luecken bzw. liefert die Grundlage, wenn gar
keine Quali-Call-Daten existieren.
"""

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError
from cc_crm.integrations.ai.anthropic_client import generate_text
from cc_crm.models.candidate import Candidate
from cc_crm.models.operational import Document
from cc_crm.services.candidates import CandidateService
from cc_crm.services.cv_extraction import extract_text_from_bytes, is_agency_letterhead
from cc_crm.services.storage import read_document_bytes

# Gleiches Limit wie bei den anderen CV-Extraktions-Aufrufen (cv_extraction.py)
# - lang genug fuer einen kompletten Lebenslauf, kurz genug um das LLM-
# Kontextfenster nicht mit typischerweise irrelevanten Endseiten (AGB-Anhaenge
# etc.) zu fluten.
MAX_CV_TEXT_CHARS = 12000

SYSTEM_PROMPT = """Du bist Recruiting-Assistent für eine auf Steuern, Wirtschaftsprüfung und
Rechtskanzleien spezialisierte Personalberatung. Du erstellst aus strukturierten
Quali-Call-Daten UND/ODER dem Rohtext eines hochgeladenen Lebenslaufs ein
anonymisiertes Profil für den Versand an Kanzleien.

DATENQUELLEN UND PRIORITÄT:
- "Quali-Call-Daten" sind von einem Menschen kuratiert und geprüft - wo sie
  ein Feld abdecken, sind sie die verlässlichere Quelle.
- "Original-CV-Text" ist der ungeprüfte Rohtext des hochgeladenen Lebenslaufs
  (Name, Adresse, Telefonnummer, echte Arbeitgebernamen etc. können darin
  vorkommen). Nutze ihn, um Lücken in den Quali-Call-Daten zu füllen oder
  wenn keine Quali-Call-Daten vorhanden sind - insbesondere für "Über die
  Person", Fachliche Qualifikationen, Lebenslauf-Stationen und Ausbildung.
- KRITISCH: der CV-Rohtext ist NICHT anonymisiert. Auch wenn dort Klarname,
  Adresse, Telefonnummer oder ein konkreter Firmenname steht, darf NICHTS
  davon 1:1 in die Ausgabe übernehmen werden - IMMER funktional/anonymisiert
  umformulieren (siehe Anonymitäts-Regel unten). Das gilt auch für Kombi-
  nationen, die in Verbindung mit anderen Angaben identifizierend wirken
  könnten (z.B. eine sehr spezifische Kanzlei+Ort+Position-Kombination).

REGELN:
- Vollständige Anonymität: keine Namen, keine Arbeitgeber-Klarnamen, keine
  Ausbildungsstätten mit Klarnamen sofern sie identifizierend wirken könnten.
  Beschreibe Stationen funktional ("mittelständische Kanzlei in NRW,
  ca. 40 Mitarbeitende" statt Firmenname).
- Das Profil muss trotzdem stark und konkret genug sein, dass eine Kanzlei
  darauf reagiert – vage Formulierungen vermeiden.
- Ton: professionell, sachlich, wie eine Kurzvorstellung — kein Marketing-Sprech.
- Nutze ausschließlich Informationen aus den gelieferten Daten (Quali-Call-Daten
  und/oder CV-Text). Erfinde nichts hinzu, auch keine plausibel klingenden
  Details.
- Wenn ein Feld leer ist, lasse den entsprechenden Punkt im Profil weg,
  statt Platzhalter zu erzeugen.
- wechselgrund und noGos NIEMALS in die Ausgabe übernehmen — nur interne Felder.
- Korrekte deutsche Groß-/Kleinschreibung und Grammatik sind Pflicht (Substantive
  großschreiben, korrekte Kommasetzung) — dieser Text geht direkt an Kanzleien,
  Fehler wirken unprofessionell.
- Gendern nach dem Feld "anrede":
  - "frau" → Kopfzeile "Kandidatin-Nr.", im Fließtext "Die Kandidatin", "sie", "ihre"
  - "herr" → Kopfzeile "Kandidat-Nr.", im Fließtext "Der Kandidat", "er", "seine"
  - "divers" oder nicht gesetzt → Kopfzeile "Kandidat:in-Nr.", im Fließtext
    neutral formulieren (z.B. "Die Person", "diese Fachkraft") statt zu raten

AUSGABEFORMAT (exakt dieses Format — 1:1 aus den bestehenden Commandeur-
Consulting-Kandidatenprofilen übernommen, NICHT davon abweichen):

## [Kandidatin-Nr. / Kandidat-Nr. / Kandidat:in-Nr., je nach anrede] [Kandidatennummer]

**Überblick**
Wohnort: [zielregion, nur Region z.B. "Raum Reutlingen", keine genaue Adresse]
Ausbildung/Weiterbildung: [ausbildungTitel]
Berufserfahrung: [berufserfahrungJahre, gerundet z.B. "15+ Jahre"]
Gehaltsvorstellung: [gehaltswunsch, gerundet z.B. "ca. 70.000 € p.a."]
Verfügbarkeit / Kündigungsfrist: [kuendigungsfrist]

**Über die Person**
[3-5 Sätze Fließtext, ausführlich und konkret (keine Floskeln). ERSTER SATZ
VERBINDLICH mit fester Eröffnungsformel, passend zu "anrede":
  - "frau" → "Unsere Kandidatin ist [Rolle/Qualifikation] mit [X Jahre/über X
    Jahre] Erfahrung in ..."
  - "herr" → "Unser Kandidat ist [Rolle/Qualifikation] mit [X Jahre/über X
    Jahre] Erfahrung in ..."
  - "divers"/nicht gesetzt → neutrale Variante, z.B. "Diese Fachkraft ist
    [Rolle/Qualifikation] mit [X Jahre/über X Jahre] Erfahrung in ..."
[Rolle/Qualifikation] aus ausbildungTitel/fachlicheSchwerpunkte/CV-Text ableiten
(z.B. "Steuerberaterin", "Rechtsanwalt", "angehender Bilanzbuchhalter"),
Erfahrungsjahre grob aus berufserfahrungJahre runden. Danach in den
folgenden Sätzen: welche Aufgabenschwerpunkte und Erfahrungstiefe bringt die
Person mit, was macht sie für eine Kanzlei interessant? Falls freitextNotizen
oder CV-Text etwas zur Wechselmotivation oder Arbeitsweise hergeben (z.B.
warum ein Wechsel angestrebt wird, besondere Stärken), darf das in einem
weiteren Satz ergänzt werden - aber nur wenn es sich anonym formulieren lässt.]

**Fachliche Qualifikationen**
[Bullet-Liste, so viele konkrete, spezifische Punkte wie die Datenlage
hergibt (typisch 6-12 bei einem vollständigen CV) - lieber ein zusätzlicher
präziser Punkt mehr als zu knapp. Jeder Punkt eine konkrete Tätigkeit/
Kompetenz aus fachlicheSchwerpunkte bzw. dem CV-Text, keine Wiederholungen,
keine generischen Sammelbegriffe ohne Substanz.]

**Lebenslauf (Auszug)**
[Zeitraum] [Rolle], [anonymisierter Arbeitgeber-Typ — NIEMALS Firmenname, nur
generische Beschreibung wie "Steuerkanzlei", "Steuerberatungsgesellschaft",
"internationale Wirtschaftskanzlei", "mittelständisches Unternehmen",
"öffentliche Institution" — aus aktuellesUmfeld/beruflicheStationen ableiten]
[eine Zeile pro Station, neueste zuerst. Format exakt: "MM/JJJJ – MM/JJJJ Rolle,
Arbeitgeber-Typ" bzw. "seit MM/JJJJ Rolle, Arbeitgeber-Typ" — KEIN Doppelpunkt
nach dem Zeitraum, KEIN Aufzählungszeichen/Bindestrich am Zeilenanfang.]

**Ausbildung & Weiterbildung**
[aus ausbildungTitel, ggf. mit Zeiträumen falls in den Daten vorhanden. Format
exakt wie oben: "JJJJ – JJJJ Bezeichnung" bzw. "JJJJ Bezeichnung" — KEIN
Doppelpunkt nach dem Zeitraum, KEIN Aufzählungszeichen/Bindestrich am
Zeilenanfang.]

**Weitere Infos**
[je EINE eigene Zeile pro Sprache im Format "Sprache: Niveau", z.B.
"Deutsch: Muttersprache" und "Englisch: Fließend" als zwei separate Zeilen -
NICHT alle Sprachen in einer einzigen "Sprachen:"-Zeile zusammenfassen. Falls
keine Sprachangaben vorhanden sind, diese Zeilen ganz weglassen.]
EDV-Kenntnisse: [Tool1 | Tool2 | Tool3, mit " | " getrennt, falls vorhanden,
sonst die Zeile ganz weglassen]

Gib ausschließlich das fertige Profil zurück, keine Erklärungen davor oder danach."""


def _total_experience_years(stations: list[dict[str, Any]]) -> float | None:
    if not stations:
        return None
    total = 0.0
    for station in stations:
        try:
            total += float(station.get("dauer_jahre") or 0)
        except (TypeError, ValueError):
            continue
    return total or None


def _build_quali_call_payload(candidate: Candidate) -> dict[str, Any]:
    # wechselgrund and no_gos are intentionally NOT included here - internal
    # only, must never reach the LLM or an outgoing document.
    return {
        "anrede": candidate.anrede.value if candidate.anrede else None,
        "rolle": candidate.job_title,
        "gehaltswunsch": candidate.salary_expectation,
        "kuendigungsfrist": candidate.notice_period,
        "region": candidate.city or candidate.postal_code,
        "profil": candidate.summary,
        "fachlicheSchwerpunkte": candidate.fachliche_schwerpunkte or [],
        "ausbildungTitel": candidate.ausbildung_titel,
        "berufserfahrungJahre": _total_experience_years(candidate.berufliche_stationen or []),
        "beruflicheStationen": candidate.berufliche_stationen or [],
        "aktuellesUmfeld": {
            "kanzleityp": candidate.aktuelles_umfeld_kanzleityp,
            "kanzleigroesse": candidate.aktuelles_umfeld_kanzleigroesse,
        },
        "freitextNotizen": candidate.freitext_notizen,
    }


def _has_content(quali_call_data: dict[str, Any]) -> bool:
    """True, wenn mindestens ein inhaltlich relevantes Quali-Call-Feld
    befuellt ist (anrede/region allein reichen nicht als Basis fuer ein
    Profil)."""
    relevant_keys = (
        "rolle",
        "gehaltswunsch",
        "kuendigungsfrist",
        "profil",
        "fachlicheSchwerpunkte",
        "ausbildungTitel",
        "beruflicheStationen",
        "freitextNotizen",
    )
    return any(quali_call_data.get(key) for key in relevant_keys)


def _latest_cv_document(session: Session, candidate_id: uuid.UUID) -> Document | None:
    return session.scalar(
        select(Document)
        .where(
            Document.owner_type == "candidate",
            Document.owner_id == candidate_id,
            Document.document_type == "cv",
        )
        .order_by(Document.created_at.desc())
        .limit(1)
    )


def _cv_text_for_candidate(session: Session, candidate_id: uuid.UUID) -> str | None:
    """Liest das zuletzt hochgeladene CV-Dokument des Kandidaten und gibt
    dessen Text zurueck - oder None, wenn kein CV vorliegt, es nicht lesbar
    ist (z.B. OneDrive-Dehydrierung, siehe operational.py::download_document),
    oder es sich erkennbar um ein von Commandeur selbst erzeugtes anonymes
    Profil statt eines echten CVs handelt (Briefkopf-Erkennung, siehe
    cv_extraction.py - so ein Dokument darf niemals als "Original-CV" in den
    Prompt einfliessen, sonst wuerde ein bereits anonymisiertes Profil als
    neue "CV-Quelle" zirkulaer wiederverwendet)."""
    document = _latest_cv_document(session, candidate_id)
    if document is None:
        return None
    try:
        content = read_document_bytes(document.storage_key)
    except OSError:
        return None
    cv_text = extract_text_from_bytes(document.filename, content)
    if not cv_text.strip() or is_agency_letterhead(cv_text):
        return None
    return cv_text[:MAX_CV_TEXT_CHARS]


class ProfileGeneratorService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.candidates = CandidateService(session)

    def generate_anonymous_profile(self, candidate_id: uuid.UUID) -> str:
        candidate = self.candidates.get(candidate_id)
        quali_call_data = _build_quali_call_payload(candidate)
        cv_text = _cv_text_for_candidate(self.session, candidate_id)

        if cv_text is None and not _has_content(quali_call_data):
            raise BusinessRuleError(
                "Für diesen Kandidaten liegt weder ein lesbares CV-Dokument noch "
                "ausgefüllte Quali-Call-Daten vor - bitte zuerst ein CV hochladen "
                "oder die Felder im Kandidatenprofil befüllen."
            )

        message_parts = [f"Kandidatennummer: {candidate.candidate_number or candidate.id}"]
        message_parts.append(
            f"Quali-Call-Daten:\n{json.dumps(quali_call_data, ensure_ascii=False, indent=2)}"
        )
        if cv_text:
            message_parts.append(f"Original-CV-Text (Rohtext, nicht anonymisiert):\n{cv_text}")
        user_message = "\n\n".join(message_parts)
        # Default max_tokens (1000) is sized for the short JSON extractions
        # elsewhere in this codebase - a full profile (6 sections, incl. a
        # bullet list and CV history) needs more room.
        return generate_text(
            system_prompt=SYSTEM_PROMPT, user_message=user_message, max_tokens=3000
        )
