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
  Details - EINZIGE Ausnahme: die Gehaltsvorstellung darf bei fehlender Angabe
  realistisch geschätzt werden (siehe eigene Regel im Ausgabeformat unten).
- Wenn ein Feld leer ist, lasse den entsprechenden Punkt im Profil weg,
  statt Platzhalter zu erzeugen - AUSNAHME: Gehaltsvorstellung (siehe eigene
  Regel unten, dort NIEMALS weglassen).
- LÄNGE - HARTE OBERGRENZE, das Profil MUSS auf eine DIN-A4-Seite passen:
  das gesamte Profil (alle Abschnitte zusammen, ohne die Überschriften)
  darf HÖCHSTENS 170 Wörter haben. Zur Orientierung: die echten Profile,
  an denen du dich orientierst, liegen bei 114-171 Wörtern INSGESAMT -
  auch die von sehr erfahrenen Kandidaten mit 20+ Jahren Berufserfahrung.
  Ein längeres Profil ist FALSCH, egal wie viel der CV hergibt. Aufteilung:
  Kurzprofil höchstens 65 Wörter, Fachliche Qualifikationen 6-9 kurze
  Stichpunkte (je 2-10 Wörter, KEINE ausformulierten Sätze), Lebenslauf
  1-5 Zeilen. Bei langer Berufshistorie NICHT jede Station auflisten,
  sondern nur die 3-5 fachlich relevantesten/aktuellsten - lieber weniger
  Stationen als ein zu langes Profil. Lieber knapp und dicht als
  vollständig: der Rest steht im CV.
- wechselgrund und noGos NIEMALS in die Ausgabe übernehmen — nur interne Felder.
- Korrekte deutsche Groß-/Kleinschreibung und Grammatik sind Pflicht (Substantive
  großschreiben, korrekte Kommasetzung) — dieser Text geht direkt an Kanzleien,
  Fehler wirken unprofessionell.
- Nebentätigkeiten/Praktika/Aushilfsjobs (z.B. im CV unter "Praktika und
  Nebentätigkeiten" gefuehrt) gehoeren NICHT ins "Lebenslauf (Auszug)", wenn
  bereits reguläre Berufserfahrung existiert - auch dann nicht, wenn die
  Nebentätigkeit zeitlich später liegt als die letzte reguläre Station.
  Ebenso keine Sprachkurse. Nur fachlich relevante Stationen aufnehmen.
- GESCHLECHT: es wird IMMER konkret männlich ODER weiblich geschrieben -
  niemals geschlechtsneutral, niemals mit Doppelpunkt/Binnen-I/Sternchen:
  - "frau" → Kopfzeile "Kandidatin-Nr.", im Fließtext "Die Kandidatin",
    "sie", "ihre", weibliche Rollenbezeichnung ("Steuerberaterin")
  - "herr" → Kopfzeile "Kandidat-Nr.", im Fließtext "Der Kandidat", "er",
    "seine", männliche Rollenbezeichnung ("Steuerberater")
  - "divers" oder NICHT GESETZT → NICHT neutral ausweichen! Leite das
    Geschlecht aus dem Vornamen bzw. den Formulierungen im CV-Rohtext ab
    (dort steht der echte Name) und schreibe dann durchgängig männlich oder
    weiblich wie oben. Ist es auch daraus nicht erkennbar, verwende die
    männliche Form als Standard.
  VERBOTEN sind daher: "Diese Fachkraft", "Die Person", "Kandidat:in",
  "Wirtschaftsprüfungsassistent:in", "Steuerberater/in" und jede andere
  neutrale oder doppelpunkt-gegenderte Formulierung - in KEINEM der
  Referenzprofile kommt so etwas vor.

AUSGABEFORMAT (exakt dieses Format — 1:1 aus den 5 NEUESTEN echten Commandeur-
Consulting-Kandidatenprofilen übernommen, NICHT davon abweichen; die drei
Beispiele am Ende dieses Prompts zeigen den kompletten Stil):

## [Kandidatin-Nr. ODER Kandidat-Nr. - nur diese beiden, NIE "Kandidat:in-Nr."] [Kandidatennummer]

**Überblick**
Wohnort: [zielregion, nur Region z.B. "Raum Reutlingen", keine genaue Adresse]
Ausbildung/Weiterbildung: [ausbildungTitel]
Berufserfahrung: [berufserfahrungJahre, IMMER im Format "X+ Jahre" (z.B. "2+
Jahre", "6+ Jahre", "15+ Jahre", "20+ Jahre") - keine Kommastellen, kein
"Über X Jahre".]
Gehaltsvorstellung: [PFLICHTFELD, NIEMALS weglassen, auch wenn gehaltswunsch
leer ist. Format "ca. X €", optional mit " p.a." oder einer Stundenangabe bei
Teilzeit, z.B. "ca. 100.000 € p.a.", "ca. 38.000 € (30h/Woche)" - NICHT
"Ab X €" oder Zusatztext wie "Je nach Job". Ist gehaltswunsch NICHT gesetzt,
einen REALISTISCHEN Marktwert schätzen (Rolle/Qualifikation, Berufserfahrung,
Region aus den vorhandenen Daten) statt die Zeile wegzulassen - grobe
Orientierung an den üblichen Gehaltsbändern in Steuer-/WP-/Rechtskanzleien:
Berufseinsteiger Steuerfachangestellte(r) ca. 38.000-48.000 €, erfahrene(r)
Steuerfachangestellte(r)/Steuerfachwirt(in) ca. 55.000-70.000 €, Bilanz-
buchhalter(in) ca. 55.000-70.000 €, Steuerberater(in) ca. 80.000-110.000 €,
Wirtschaftsprüfer(in)/Prüfungsleiter(in) ca. 90.000-130.000 €, Partner(in)
deutlich höher. Diese Schätzung wird vor dem Versand ohnehin von einem
Menschen gegengeprüft - lieber ein plausibler Schätzwert als eine leere
Zeile.]
Verfügbarkeit: [Wert, z.B. "Kurzfristig", "Nach Absprache" oder ein Datum -
NUR wenn keine echte Kündigungsfrist bekannt ist. Ist eine Kündigungsfrist
bekannt, diese Zeile durch "Verfügbarkeit / Kündigungsfrist: [X Monate zum
Monatsende]" ERSETZEN statt beide Zeilen zu zeigen.]

**Kurzprofil**
[EIN dichter Absatz, GENAU 3-4 Sätze, HÖCHSTENS 65 Wörter (die echten
Referenzprofile liegen bei 48-67 Wörtern - auch bei 20+ Jahren Erfahrung).
Satz 1 VERBINDLICH mit exakt dieser Eröffnung, je nach Geschlecht (siehe
GESCHLECHT-Regel oben - bei fehlender "anrede" aus dem CV ableiten, NIEMALS
"Diese Fachkraft" oder eine andere neutrale Formulierung):
  - weiblich → "Die Kandidatin ist [Rolle] mit [Erfahrungsangabe] ..."
  - männlich → "Der Kandidat ist [Rolle] mit [Erfahrungsangabe] ..."
[Rolle] aus ausbildungTitel/fachlicheSchwerpunkte/CV-Text ableiten, im
korrekten Genus ("Steuerberaterin"/"Steuerberater"). [Erfahrungsangabe]
natürlichsprachlich, NICHT zwingend "X+ Jahre" wie im Überblick oben - je
nach Seniorität z.B. "langjähriger Berufserfahrung", "über 20 Jahren
Berufserfahrung", "erster Berufserfahrung".
Satz 2-3: aktuelle/letzte Station - was macht die Person dort konkret,
welche fachlichen Schwerpunkte. Satz 4 (optional, nur wenn CV-Text/
freitextNotizen es anonym hergeben): Wechselgrund oder Zusatzkontext, z.B.
"Aufgrund einer Umstrukturierung in ihrer aktuellen Kanzlei sucht sie nun
nach einer neuen Herausforderung.", "sucht eine Kanzlei, bei der er sich
fachlich und persönlich weiterentwickeln kann."
KEINE Aufzählung von Branchen, Standorten, Teamgrößen, Budgets oder
Prüfungsstandards im Kurzprofil - solche Details gehören, wenn überhaupt,
als kurzer Stichpunkt in die Fachlichen Qualifikationen.]

**Fachliche Qualifikationen**
[Bullet-Liste, 6-9 Punkte. Jeder Punkt ein KURZER Stichpunkt von 2-10
Wörtern (so wie in den Beispielen unten: "Laufende Finanzbuchhaltung",
"Begleitung von Betriebsprüfungen") - KEINE ausformulierten Sätze, keine
Aufzählung mehrerer Themen in einem Punkt. NICHT künstlich aufblähen, wenn
der CV nicht mehr hergibt (bei jungen Kandidaten sind 6 Punkte normal). Die
Liste darf Themen aus dem Kurzprofil aufgreifen und in knappe Einzelpunkte
herunterbrechen (kein 1:1 kopierter Satz) - "keine Überschneidung" ist NICHT
das Ziel. Keine Wiederholungen, keine generischen Sammelbegriffe ohne
Substanz.]

**Lebenslauf (Auszug)**
[Zeitraum] [Rolle], [anonymisierter Arbeitgeber-Typ — NIEMALS Firmenname, nur
generische Beschreibung wie "Steuerkanzlei", "Steuerberatungsgesellschaft",
"internationale Wirtschaftskanzlei", "mittelständisches Unternehmen",
"öffentliche Institution" — aus aktuellesUmfeld/beruflicheStationen ableiten]
[eine Zeile pro Station, neueste zuerst, HÖCHSTENS 5 Zeilen - nur fachlich
relevante Stationen (siehe Regel oben zu Nebentätigkeiten/Praktika/
Sprachkursen), bei kurzer Historie reicht auch nur EINE Zeile (mehrere
Referenzprofile haben genau eine). Ältere/weniger relevante Stationen
ersatzlos weglassen statt die Liste zu verlängern. Format exakt:
"MM/JJJJ – MM/JJJJ Rolle, Arbeitgeber-Typ" bzw. "seit MM/JJJJ Rolle,
Arbeitgeber-Typ" — KEIN Doppelpunkt nach dem Zeitraum, KEIN
Aufzählungszeichen/Bindestrich am Zeilenanfang.]

**Ausbildung & Weiterbildung**
[aus ausbildungTitel, ggf. mit Zeiträumen falls in den Daten vorhanden. Format
exakt wie oben: "JJJJ – JJJJ Bezeichnung" bzw. "JJJJ Bezeichnung" — KEIN
Doppelpunkt nach dem Zeitraum, KEIN Aufzählungszeichen/Bindestrich am
Zeilenanfang.]

**Weitere Infos**
[Knapp halten, meist 1-2 Zeilen insgesamt - keine granulare Auflistung. Für
Sprachen ENTWEDER mehrere Zeilen im Format "Sprache: Niveau" (z.B. "Deutsch:
Muttersprache") ODER eine einzige zusammengefasste Zeile "Sprachen: Deutsch
(Muttersprache), Englisch (fließend)" - beides ist zulässig, wählen was zur
Datenlage passt. Falls keine Sprachangaben vorhanden sind, weglassen.]
[EDV/Tools-Zeile im Format "EDV: Tool1, Tool2" oder "Tools: Tool1, Tool2" (mit
", " getrennt, NICHT " | "), NUR mit tatsächlich im CV genannten Systemen -
nichts erfinden oder aufblähen. Ohne Angaben im CV die Zeile ganz weglassen.]

Gib ausschließlich das fertige Profil zurück, keine Erklärungen davor oder danach.

DREI STILVORBILDER (echte, bereits anonyme Commandeur-Consulting-Profile,
exakt in diesem Stil/Format nachbilden - unterschiedliche Rollen/Seniorität):

---BEISPIEL 1 (Steuerfachangestellte, viel Erfahrung, Teilzeit-Gehaltsangabe)---
## Kandidatin-Nr. 4455

**Überblick**
Wohnort: Raum Bonn
Ausbildung/Weiterbildung: Steuerfachangestellte
Berufserfahrung: 11+ Jahre
Gehaltsvorstellung: ca. 38.000 € (30h/Woche)
Verfügbarkeit: Kurzfristig

**Kurzprofil**
Die Kandidatin ist Steuerfachangestellte mit langjähriger Berufserfahrung im Tagesgeschäft einer Steuerberaterkanzlei. Sie unterstützt Mandate in der laufenden Finanzbuchhaltung sowie in der Kundenberatung und -betreuung. Zuvor sammelte sie mehrjährige Erfahrung in der kaufmännischen Sachbearbeitung und Büroorganisation. Aufgrund einer Umstrukturierung in ihrer aktuellen Kanzlei sucht sie nun nach einer neuen Herausforderung.

**Fachliche Qualifikationen**
Laufende Finanzbuchhaltung
Erstellung von Steuererklärungen
Erstellung von Jahresabschlüssen
Büroorganisation und Sachbearbeitung
Kundenberatung und -betreuung
Korrespondenz mit Mandanten und Finanzämtern
Sicherer Umgang mit MS Office

**Lebenslauf (Auszug)**
seit 2015 Steuerfachangestellte, Steuerberaterkanzlei

**Ausbildung & Weiterbildung**
Umschulung zur Steuerfachangestellten
Studium der Betriebswirtschaft (Diplom-Betriebswirtin)

**Weitere Infos**
EDV: MS Office, DATEV

---BEISPIEL 2 (Steuerberater, baut Mandantenstamm auf)---
## Kandidat-Nr. 4453

**Überblick**
Wohnort: Raum Heidelberg
Ausbildung/Weiterbildung: Steuerberater
Berufserfahrung: 6+ Jahre
Gehaltsvorstellung: ca. 100.000 €
Verfügbarkeit / Kündigungsfrist: 3 Monate zum Monatsende

**Kurzprofil**
Der Kandidat ist Steuerberater mit Erfahrung in der steuerlichen Betreuung von Unternehmen und Privatpersonen. Er baut aktuell einen eigenen Mandantenstamm auf und betreut diesen eigenständig. Zu seinen Schwerpunkten zählen die Erstellung und das Review von Jahresabschlüssen und Steuererklärungen, die laufende steuerliche Beratung sowie die Begleitung von Betriebsprüfungen. Darüber hinaus verfügt er über Erfahrung in der steuerlichen Gestaltungsberatung und der Optimierung bestehender Prozesse.

**Fachliche Qualifikationen**
Eigenständiger Aufbau und Betreuung eines Mandantenstamms
Laufende und gestaltende steuerliche Beratung von Unternehmen und Privatpersonen
Erstellung und Review von Jahresabschlüssen verschiedener Rechtsformen
Erstellung und Review betrieblicher und privater Steuererklärungen
Begleitung von Betriebsprüfungen und Korrespondenz mit Finanzbehörden
Digitalisierung und Optimierung von Kanzlei- und Mandantenprozessen

**Lebenslauf (Auszug)**
seit 04/2025 Steuerberater, Steuerberatungsgesellschaft
09/2020 – 03/2025 Steuerfachangestellter, Steuerberatungsgesellschaft

**Ausbildung & Weiterbildung**
2024 – 2025 Steuerberaterexamen
2020 – 2022 Ausbildung zum Steuerfachangestellten
2015 – 2018 Bachelor of Arts – BWL

**Weitere Infos**
Sprachen: Deutsch (Muttersprache), Englisch (fließend)
EDV: MS Office, ADDISON

---BEISPIEL 3 (Steuerfachangestellter, Berufseinsteiger, konkretes Verfügbarkeitsdatum)---
## Kandidat-Nr. 4053

**Überblick**
Wohnort: Raum München
Ausbildung/Weiterbildung: Steuerfachangestellter
Berufserfahrung: 2+ Jahre
Gehaltsvorstellung: ca. 48.000 €
Verfügbarkeit: 01. September 2026

**Kurzprofil**
Der Kandidat ist Steuerfachangestellter mit erster Berufserfahrung im Tagesgeschäft einer Steuerberatungskanzlei. Er unterstützt Mandate in der laufenden Finanzbuchhaltung, bei der Erstellung von Steuererklärungen sowie bei vorbereitenden Tätigkeiten im Rahmen von Jahresabschlüssen. Aktuell befindet er sich in der Weiterbildung zum Bilanzbuchhalter und sucht eine Kanzlei, bei der er sich fachlich und persönlich weiterentwickeln kann.

**Fachliche Qualifikationen**
Laufende Finanzbuchhaltung
Erstellung von Steuererklärungen
Bearbeitung steuerlicher Bescheide
Mitwirkung bei der Erstellung von Jahresabschlüssen
Korrespondenz mit Mandanten, Finanzämtern und Behörden
Sicherer Umgang mit DATEV und MS Office

**Lebenslauf (Auszug)**
seit 2024 Steuerfachangestellter, Steuerberatungsgesellschaft

**Ausbildung & Weiterbildung**
Ausbildung zum Steuerfachangestellten
Weiterbildung zum Bilanzbuchhalter (laufend)

**Weitere Infos**
EDV: digitale Kanzleisysteme, MS Office"""


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


def _berufliche_stationen_for_profile(candidate: Candidate) -> list[dict[str, Any]]:
    """Titelschutz-Korrektur Schritt 2, Sperre fuers anonyme Profil: wenn
    candidate.rollen_unbestaetigt gesetzt ist, wird das "rolle"-Feld je
    Station aus der Nutzlast entfernt, BEVOR sie ans LLM geht - das ist die
    vom Modell selbst erzeugte Klassifikation, genau dieselbe, die im
    Titelschutz-Audit als unbelegt markiert wurde (siehe scripts/
    audit_titelschutz_unverified_roles.py). Bewusst WEGLASSEN statt nur zu
    warnen (und nicht bloss die eine unbelegte Rolle, sondern alle Stationen-
    Rollen dieses Kandidaten): ein Warnhinweis kann in einem hektischen
    Arbeitsalltag uebersehen werden, ein weggelassenes Feld nicht - ein
    unbestaetigter geschuetzter Titel darf UNTER KEINEN UMSTAENDEN in ein
    ausgehendes Dokument wandern, unabhaengig davon, ob jemand eine Warnung
    wahrnimmt. Das Frontend zeigt zusaetzlich einen sichtbaren Hinweis, siehe
    AnonymousProfilePanel - Weglassen und Sichtbarkeit schliessen sich nicht
    aus."""
    stationen = candidate.berufliche_stationen or []
    if not candidate.rollen_unbestaetigt:
        return stationen
    return [{k: v for k, v in station.items() if k != "rolle"} for station in stationen]


def _build_quali_call_payload(candidate: Candidate) -> dict[str, Any]:
    # wechselgrund and no_gos are intentionally NOT included here - internal
    # only, must never reach the LLM or an outgoing document.
    berufliche_stationen = _berufliche_stationen_for_profile(candidate)
    return {
        "anrede": candidate.anrede.value if candidate.anrede else None,
        "rolle": candidate.job_title,
        "gehaltswunsch": candidate.salary_expectation,
        "kuendigungsfrist": candidate.notice_period,
        "region": candidate.city or candidate.postal_code,
        "profil": candidate.summary,
        "fachlicheSchwerpunkte": candidate.fachliche_schwerpunkte or [],
        "ausbildungTitel": candidate.ausbildung_titel,
        "berufserfahrungJahre": _total_experience_years(berufliche_stationen),
        "beruflicheStationen": berufliche_stationen,
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
