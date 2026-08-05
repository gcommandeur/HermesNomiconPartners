"""Extraktion strukturierter Kandidatenfelder (PLZ, Ort, Telefon, Rolle,
Qualifikation, Ausbildung) aus einem hochgeladenen CV-Dokument (Phase M,
Punkt 2/4). Nutzt denselben LLM-Baustein wie der Profil-Generator (Phase 2,
`services/profile_generator.py`) - ein strukturierter Extraktions-Prompt ist
bei Rolle/Qualifikation als Freitext deutlich zuverlässiger als Regex.

WICHTIG: Manche im System vorhandenen "CVs" sind tatsaechlich von Commandeur
selbst erzeugte, anonymisierte Bewerberprofile (Briefkopf "Commandeur
Consulting GmbH, Talstraße 112, 41199 Mönchengladbach", siehe
profile_docx_export.py) und NICHT das Originaldokument des Kandidaten. Aus
so einem Dokument darf NIE eine Adresse/Telefonnummer uebernommen werden -
das waere die Adresse der eigenen Agentur, nicht die des Kandidaten. Der
Check auf "Commandeur Consulting GmbH" im Text ist absichtlich zusaetzlich
zur Prompt-Instruktion als Code-Check umgesetzt (Verteidigung in der Tiefe -
ein LLM-Fehler bei der Erkennung darf keine Agenturadresse durchrutschen
lassen)."""

from __future__ import annotations

import base64
import json
import logging
import re
from io import BytesIO
from pathlib import Path
from typing import Any

import docx
from pypdf import PdfReader

from cc_crm.integrations.ai.anthropic_client import generate_text, generate_text_with_image
from cc_crm.models.enums import Rolle

logger = logging.getLogger("cc_crm.cv_extraction")

AGENCY_LETTERHEAD_MARKER = "Commandeur Consulting GmbH"

# Werden diese Felder trotz Text-Extraktion nicht gefunden, gilt das als
# Hinweis auf eine defekte Font-Kodierung im PDF (siehe extract_text_from_bytes)
# und loest den Vision-Fallback aus (siehe extract_candidate_fields) - Nutzer-
# Vorgabe: "wenn bestimmte Standardinfos: Name, Rolle, Telefon, PLZ nicht
# gelesen werden, wird es nochmal analysiert".
_STANDARD_FIELDS_TO_VERIFY = ("first_name", "last_name", "job_title", "phone", "postal_code")

# Zentrale Liste aller Kandidaten-Spalten, die aus einem CV befuellt werden
# koennen - EINZIGE Stelle, die ein neues strukturiertes Feld kennen muss
# (CandidateService.suggest_cv_fields/auto_fill_from_cv, der /cv-preview-
# Endpoint und scripts/backfill_cv_rollen_und_schwerpunkte.py leiten sich
# alle hieraus ab, statt das Feld an mehreren Stellen einzeln aufzuzaehlen).
# Feld MUSS als gleichnamiges Attribut sowohl auf Candidate
# (models/candidate.py) als auch auf CvExtractionSuggestion
# (schemas/candidate.py) existieren. Freitext-/Analysefelder, die (noch)
# keine eigene Kandidaten-Spalte haben (z.B. erfahrungen_zusammenfassung,
# siehe Prompt unten), gehoeren NICHT hierher - die landen ausschliesslich
# in cv_extraction_raw (siehe CandidateService.auto_fill_from_cv) und stehen
# darueber trotzdem jeder kuenftigen Funktion zur Verfuegung, ganz ohne neue
# Spalte/Migration.
CV_STRUCTURED_FIELDS: tuple[str, ...] = (
    "first_name",
    "last_name",
    "email",
    "postal_code",
    "city",
    "phone",
    "job_title",
    "qualification",
    "ausbildung_titel",
    "fachliche_schwerpunkte",
    "rollen",
    "current_employer_internal",
    "berufliche_stationen",
)

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

_VALID_ROLLEN = {rolle.value for rolle in Rolle}

_FIELD_EXTRACTION_SYSTEM_PROMPT = """Du extrahierst strukturierte Kontakt- und Rollendaten aus einem
Lebenslauf-Text für ein Recruiting-CRM (Fokus Steuern/Wirtschaftsprüfung/Recht).
Der Text stammt aus einer automatischen PDF/DOCX-Extraktion und kann Layout-
Artefakte enthalten (z.B. Buchstaben durch Leerzeichen getrennt wie "J a n a
G u ß e r" statt "Jana Gußer", oder einzelne Sonderzeichen/Umlaute, die als
Platzhalter wie "�" erscheinen, weil die Schriftart im PDF keine korrekte
Unicode-Zuordnung hat) - erkenne solche Artefakte und rekonstruiere den
naheliegenden echten Namen/Text daraus, erfinde aber keine Informationen, die
sich nicht aus dem Kontext ableiten lassen.

Gib AUSSCHLIESSLICH ein JSON-Objekt zurück (kein Markdown-Codeblock, keine
Erklärung davor/danach), mit exakt diesen Schlüsseln:
{
  "first_name": "<Vorname der Person, oder null>",
  "last_name": "<Nachname der Person, oder null>",
  "email": "<E-Mail-Adresse der Person, oder null>",
  "postal_code": "<deutsche Postleitzahl, 5 Ziffern, oder null>",
  "city": "<Ort, oder null>",
  "phone": "<Telefonnummer wie im Text, oder null>",
  "job_title": "<aktuelle/letzte Berufsbezeichnung, kurz, oder null>",
  "qualification": "<Qualifikation/Berufsabschluss, kurz z.B. 'Steuerberater', oder null>",
  "rollen": ["<eine oder mehrere von: steuerfachangestellte, steuerfachwirt,
    bilanzbuchhalter, steuerberater, partner, pruefungsassistent,
    pruefungsleiter, wirtschaftspruefer, rechtsfachangestellte,
    rechtsanwalt, sonstige>"],
  "current_employer_internal": "<Klarname des aktuellen/letzten Arbeitgebers, oder null>",
  "berufliche_stationen": [
    {
      "rolle": "<GENAU EINER der Werte oben, oder null>",
      "kanzleityp": "<Art des Arbeitgebers dieser Station, kurz, z.B.
        'Steuerkanzlei', 'Wirtschaftsprüfungsgesellschaft',
        'Anwaltskanzlei', 'Big4', 'Unternehmen (interne Steuerabteilung)'>",
      "kanzleigroesse": "<Größenordnung dieser Station, kurz, z.B.
        '5-10 Mitarbeitende', 'Big4', 'Einzelkanzlei' - grobe Schätzung
        reicht, wenn nicht explizit genannt>",
      "dauer_jahre": <Dauer dieser Station in Jahren als Zahl, geschätzt
        aus den genannten Zeiträumen>
    }
  ],
  "ausbildung_titel": "<siehe Regeln unten, oder null>",
  "fachliche_schwerpunkte": ["<fachlicher Schwerpunkt 1>", "<fachlicher Schwerpunkt 2>", "..."],
  "erfahrungen_zusammenfassung": "<2-3 Saetze Fliesstext zur bisherigen Berufserfahrung, oder null>"
}

REGELN:
- Nutze NUR Informationen, die explizit im Text stehen (auch wenn durch Layout-
  Artefakte leicht verzerrt, siehe oben). Erfinde nichts.
- Falls ein Feld nicht sicher aus dem Text hervorgeht, setze null statt zu raten.
- first_name/last_name: der Name der Person, der der Lebenslauf gehört - meist
  in der Kopfzeile/Überschrift zu finden, nicht der Name eines Sachbearbeiters
  oder einer Kontaktperson bei einem früheren Arbeitgeber.
- job_title/qualification: nur die aktuellste/letzte Position, nicht die gesamte Berufshistorie.
- qualification: falls die Person mehrere aktuell gültige Berufsbezeichnungen/
  -abschlüsse hat (z.B. "Steuerberater" UND "Wirtschaftsprüfer"), beide durch
  " / " getrennt angeben. qualification bleibt ein reines Freitext-Anzeigefeld -
  die STRUKTURIERTE Mehrfachrollen-Information gehört in "rollen", nicht hierher.

ROLLEN-TAXONOMIE (fuer "rollen" UND fuer "rolle" je Station in
berufliche_stationen) - typische Aufgaben/Signale je Rolle:
- steuerfachangestellte: Finanzbuchhaltung, Lohn-/Gehaltsabrechnung,
  Steuererklärungen (privat/betrieblich), Vorbereitung Jahresabschluss.
- steuerfachwirt: wie steuerfachangestellte, PLUS eigenständige Monats-/
  Jahresabschlüsse, Bilanzen, Bank-/Finanzierungsgespräche.
- bilanzbuchhalter: Jahresabschluss nach HGB (teils IFRS), Rückstellungen,
  Abgrenzungen, Anlagenbuchhaltung.
- steuerberater: steuerrechtliche Beratung, Steueroptimierung,
  Jahresabschlüsse, Vertretung vor Finanzamt/Finanzgericht.
- partner: KEIN Anzeigen-/Aufgabenprofil - nur über explizite Keyword-
  Trigger erkennbar: "Partner seit", "Equity Partner", "Sozius", "Partner
  der Kanzlei". Ohne einen dieser expliziten Begriffe NICHT vergeben, auch
  wenn die Person sehr senior klingt.
- pruefungsassistent: Mitwirkung bei Jahres-/Konzernabschlussprüfungen,
  Prüfungsvorbereitung (Einstiegs-/frühe Senioritätsstufe).
- pruefungsleiter: Planung/Durchführung von Abschlussprüfungen,
  Teamführung, Mandatsverantwortung (mittlere Senioritätsstufe, Titel wie
  "Manager"/"Senior Manager").
- wirtschaftspruefer: Jahresabschlussprüfung, Bestätigungsvermerke,
  Rechnungslegung HGB/IFRS - setzt ein bestandenes WP-Examen voraus.
- rechtsfachangestellte: Mandantenkorrespondenz, Schriftverkehr mit
  Gerichten/Behörden, Fristenkontrolle, Aktenverwaltung, RVG-Abrechnung.
- rechtsanwalt: Vertragsgestaltung/-verhandlung, Mandantenvertretung vor
  Gericht, Zulassung als Rechtsanwalt/-anwältin. Das konkrete Rechtsgebiet
  (z.B. Arbeitsrecht, Gesellschaftsrecht, Steuerrecht, Familienrecht)
  gehört NICHT in "rollen", sondern als eigener Eintrag in
  fachliche_schwerpunkte.
- sonstige: erkennbar fachfremde oder nicht zuordenbare Rolle.

ABGRENZUNGSREGELN (wichtig gegen Fehlklassifikation):
- steuerfachangestellte vs. steuerfachwirt vs. bilanzbuchhalter: die
  Aufgaben überschneiden sich stark - entscheide primär über den im CV
  genannten FORMALEN ABSCHLUSS/TITEL, nicht nur über die Tätigkeitsbeschreibung.
- pruefungsassistent -> pruefungsleiter -> wirtschaftspruefer ist eine
  Seniorität-Leiter, keine 3 unabhängigen Rollen - unterscheide über
  Berufsjahre/Titel im Text ("Assistent" vs. "Manager"/"Senior Manager" vs.
  "WP-Examen").
- partner wird NIEMALS aus einer Aufgabenbeschreibung abgeleitet, nur aus
  den oben genannten expliziten Keywords.

rollen: LISTE der zeitlich LETZTEN RELEVANTEN Rolle(n) - nicht zwingend aus
der allerletzten Station im CV abgeleitet, sondern aus der zeitlich letzten
Station, bei der eine unserer 10 Zielrollen ausgeübt wurde. Folgt danach noch
eine fachfremde Station (rolle "sonstige"), bleibt die davor liegende
relevante Rolle trotzdem in "rollen" stehen - Beispiel: 4,5 Jahre
Prüfungsassistent, danach kurzzeitig fachfremd gearbeitet -> rollen:
["pruefungsassistent"], NICHT leer. Waren zum Zeitpunkt dieser letzten
relevanten Station mehrere Zielrollen gleichzeitig gültig (z.B.
Rechtsanwalt und Steuerberater am selben Ort/derselben Station), alle in die
Liste aufnehmen - Signale dafür: "Steuerberater und Rechtsanwalt", eine
Aufzählung von Titeln direkt unter dem Namen, mehrere Kammerzulassungen
(z.B. Steuerberaterkammer UND Rechtsanwaltskammer). Rollen aus noch weiter
zurückliegenden, bereits durch eine SPÄTERE relevante Station abgelösten
Stationen NICHT zusätzlich aufnehmen (Beispiel: erst Steuerfachangestellte,
danach Weiterqualifikation zum Bilanzbuchhalter -> rollen:
["bilanzbuchhalter"], NICHT beide) - nur die zeitlich letzte relevante Rolle
zählt hier, die vollständige Historie inkl. aller früheren Rollen steht
ohnehin unverkürzt in berufliche_stationen. Leeres Array nur, wenn in der
GESAMTEN Historie keine der 10 Rollen erkennbar ist (nicht "sonstige"
erzwingen, wenn wirklich nichts passt).

current_employer_internal: der Klarname des aktuellen/letzten Arbeitgebers
(wird intern gespeichert, NIE automatisch in ausgehende Dokumente
übernommen) - falls der Text erkennbar ein anonymisiertes Bewerberprofil
einer Personalberatung ist (siehe Briefkopf-Regel unten), ist der
Arbeitgeber dort ohnehin meist schon anonymisiert/generisch beschrieben; in
diesem Fall diese generische Beschreibung übernehmen, keinen Namen erfinden.

berufliche_stationen: ALLE im CV erkennbaren beruflichen Stationen (nicht
nur die aktuellste). REIHENFOLGE VERBINDLICH: neueste/aktuellste Station
zuerst, älteste Station als letzter Listeneintrag - unabhängig davon, in
welcher Reihenfolge sie im CV-Text auftauchen. Diese feste Reihenfolge ist
die Grundlage für die Ableitung von "rollen" oben (erste Station in dieser
Liste mit einer der 10 Zielrollen = die zeitlich letzte relevante Rolle).
Jede Station braucht kanzleityp UND kanzleigroesse (grobe Schätzung reicht)
- eine Station ohne diese beiden Angaben lieber ganz weglassen, statt sie zu
erfinden.

ausbildung_titel: NUR konkrete fachbezogene Ausbildungs-/Prüfungsabschlüsse
mit Institution/Jahr, wo im Text vorhanden, z.B. "Steuerberaterprüfung
bestanden 2019", "Bilanzbuchhalter/in IHK", "WP-Examen", "Fachanwalt für
Arbeitsrecht". NICHT hierher gehören allgemeine Studienabschlüsse ohne
Fachbezug (z.B. bloßes "Bachelor BWL" ohne weiteren Kontext) oder
Schulabschlüsse (Abitur etc.) - in diesem Fall null setzen statt eines
schwachen Treffers.

- fachliche_schwerpunkte: anders als job_title/qualification aus dem GESAMTEN
  Lebenslauf (nicht nur der aktuellsten Position) - konkrete, inhaltlich
  greifbare fachliche Schwerpunkte/Fähigkeiten. Orientierung je Rolle
  (Beispiele, keine starre Pflichtliste - reale CV-Inhalte gehen vor):
  steuerfachangestellte/steuerfachwirt: Finanzbuchhaltung, Lohnbuchhaltung,
  Steuererklärungen, DATEV, BWA; bilanzbuchhalter: Bilanzierung HGB, IFRS,
  Anlagenbuchhaltung, Rückstellungen; steuerberater: Umsatzsteuer,
  Jahresabschluss, Vertretung Finanzamt/Finanzgericht, betriebswirtschaftliche
  Beratung; partner: Mandatsverantwortung, Akquise/Business Development,
  Personalverantwortung; prüfungsassistent/-leiter/wirtschaftsprüfer:
  Abschlussprüfung, Konzernabschluss, Bestätigungsvermerk, HGB, IFRS;
  rechtsfachangestellte: Fristenkontrolle, RVG-Abrechnung, Aktenverwaltung;
  rechtsanwalt: Vertragsrecht, Prozessvertretung, PLUS das konkrete
  Rechtsgebiet als eigener Tag (z.B. "Arbeitsrecht", "Gesellschaftsrecht").
  DATEV taucht rollenübergreifend als Software-Skill auf. KEINE generischen
  Floskeln wie "Teamfähigkeit", "Kommunikationsstärke" oder "selbstständiges
  Arbeiten" - nur fachlich/inhaltlich verwertbare Stichpunkte, kurz gehalten
  (2-6 Wörter je Eintrag). Leeres Array, falls nichts Konkretes im Text
  erkennbar ist.
- erfahrungen_zusammenfassung: sachlicher Fliesstext-Überblick über die
  bisherige Berufserfahrung aus dem GESAMTEN Lebenslauf (Stationen, Branchen,
  ungefähre Dauer), kein Marketing-/Bewerbungssprech, keine Wertung. Dient als
  kurze Orientierung für jemanden, der das CV noch nicht gelesen hat.
- Name/Adresse/Telefon/E-Mail: NIEMALS übernehmen, wenn der Text erkennbar ein
  anonymisiertes, von einer Personalberatung selbst erstelltes Kandidatenprofil
  ist (Briefkopf/Fußzeile mit der Adresse der Beratung statt der Adresse der
  Person) statt das Original-CV der Person - in diesem Fall first_name,
  last_name, email, postal_code, city und phone auf null setzen, auch wenn im
  Text irgendein Name/eine Adresse steht (das wäre der Name/die Adresse der
  Beratung bzw. eines dortigen Ansprechpartners, nicht der Person)."""


def extract_text_from_bytes(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        document = docx.Document(BytesIO(content))
        return "\n".join(
            paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()
        )
    if suffix == ".pdf":
        reader = PdfReader(BytesIO(content))
        # "layout" statt des pypdf-Default-Modus: der Default reiht Glyphen oft
        # strikt nach ihrer Position in der Content-Stream-Reihenfolge auf, was
        # bei vielen CVs (Kopfzeile mit grosszuegigem Buchstabenabstand, mehr-
        # spaltige Layouts) zu falsch getrenntem Text fuehrt, z.B. "J a n a
        # G u ß e r" statt "Jana Gußer" - "layout" rekonstruiert stattdessen die
        # sichtbare Seitenposition und haelt zusammengehoerige Woerter zusammen.
        return "\n".join(
            page.extract_text(extraction_mode="layout") or "" for page in reader.pages
        )
    return content.decode("utf-8", errors="ignore")


def is_agency_letterhead(cv_text: str) -> bool:
    return AGENCY_LETTERHEAD_MARKER.casefold() in cv_text.casefold()


def _parse_json_response(raw: str) -> dict[str, Any]:
    fenced = _JSON_FENCE.search(raw)
    payload = fenced.group(1) if fenced else raw.strip()
    parsed: dict[str, Any] = json.loads(payload)
    return parsed


def _render_first_pdf_page_png_base64(content: bytes) -> str:
    """Rendert die erste PDF-Seite als PNG (base64) fuer den Vision-Fallback.
    scale=2.0 entspricht ca. 150 DPI - fuer Fliesstext gut lesbar, haelt das
    Bild (und damit die Tokenkosten des Vision-Calls) aber klein. Kontakt-
    daten stehen bei einem CV praktisch immer auf der ersten Seite, ein
    Mehrseiten-Rendering waere unnoetiger Mehraufwand."""
    import pypdfium2 as pdfium  # lazy: nur fuer den seltenen Fallback noetig

    pdf = pdfium.PdfDocument(content)
    try:
        page = pdf[0]
        bitmap = page.render(scale=2.0)
        pil_image = bitmap.to_pil()
        buffer = BytesIO()
        pil_image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    finally:
        pdf.close()


def _extract_fields_via_vision(content: bytes) -> dict[str, Any]:
    """Fallback fuer PDFs mit defekter Font-Kodierung (siehe Modul-Docstring
    zu extract_text_from_bytes): rendert die erste Seite als Bild und liest
    sie per Vision aus, statt sich weiter auf den (in diesem Fall
    unzuverlaessigen) Text-Layer zu verlassen. Gleiches Schema/Prompt wie die
    text-basierte Extraktion, nur mit Bild statt Text als Eingabe.

    timeout=20.0 (statt Standard 45.0): dieser Call laeuft IMMER als
    ZWEITER, sequenzieller Anthropic-Call innerhalb desselben HTTP-Requests
    (siehe extract_candidate_fields) - addiert sich also zur Laufzeit des
    vorausgegangenen Text-Extraktions-Calls. Ohne engeres Timeout hier kann
    die Summe beider Calls den App-Platform-Gateway-Timeout ueberschreiten
    (live beobachtet: 504 "origin_connection_timed_out" bei
    /candidates/cv-preview, nachdem max_tokens fuer beide Calls von 750 auf
    1500 verdoppelt wurde)."""
    image_base64 = _render_first_pdf_page_png_base64(content)
    raw = generate_text_with_image(
        system_prompt=_FIELD_EXTRACTION_SYSTEM_PROMPT,
        user_message="Lies die Felder aus dem Bild der ersten Lebenslauf-Seite aus.",
        image_base64=image_base64,
        max_tokens=1500,
        timeout=20.0,
    )
    return _parse_json_response(raw)


def _normalize_rollen(raw: Any) -> list[str]:
    """Filtert eine vom Modell gelieferte rollen-Liste auf bekannte
    Rolle-Enum-Werte (siehe models/enums.py::Rolle) - haelt sich das Modell
    nicht exakt an die vorgegebenen Werte (z.B. Grossschreibung, ein nicht
    vorgesehener Freitext-Wert), wird der einzelne Eintrag verworfen statt
    die gesamte Extraktion an einem Pydantic-Validierungsfehler scheitern zu
    lassen."""
    if not isinstance(raw, list):
        return []
    normalized: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        candidate = item.strip().lower()
        if candidate in _VALID_ROLLEN and candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _normalize_berufliche_stationen(raw: Any) -> list[dict[str, Any]]:
    """Validiert/normalisiert die vom Modell gelieferten Stationen. kanzleityp
    und kanzleigroesse sind in schemas/candidate.py::BeruflicheStation
    Pflichtfelder (min_length=1) - eine Station ohne diese beiden Angaben
    wird hier verworfen statt mit erfundenem Platzhaltertext aufgefuellt
    (Prompt-Regel: nichts erfinden). rolle wird wie bei _normalize_rollen auf
    bekannte Enum-Werte geprueft, ein unbekannter/fehlender Wert wird null."""
    if not isinstance(raw, list):
        return []
    stations: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kanzleityp = item.get("kanzleityp")
        kanzleigroesse = item.get("kanzleigroesse")
        if not (isinstance(kanzleityp, str) and kanzleityp.strip()):
            continue
        if not (isinstance(kanzleigroesse, str) and kanzleigroesse.strip()):
            continue
        try:
            dauer_jahre = float(item.get("dauer_jahre") or 0)
        except (TypeError, ValueError):
            dauer_jahre = 0.0
        rolle = item.get("rolle")
        rolle_normalized = rolle.strip().lower() if isinstance(rolle, str) else None
        if rolle_normalized not in _VALID_ROLLEN:
            rolle_normalized = None
        stations.append(
            {
                "kanzleityp": kanzleityp.strip(),
                "kanzleigroesse": kanzleigroesse.strip(),
                "dauer_jahre": max(dauer_jahre, 0.0),
                "rolle": rolle_normalized,
            }
        )
    return stations


def extract_candidate_fields(
    cv_text: str, *, filename: str | None = None, content: bytes | None = None
) -> dict[str, Any]:
    """Fuer Punkt 2 (manueller Einzel-Upload): Name/E-Mail/PLZ/Ort/Telefon/
    Rolle/Qualifikation/Ausbildung. Alle personenbezogenen Felder werden
    zusaetzlich zur Prompt-Instruktion hart auf None gesetzt, wenn der
    Agentur-Briefkopf erkannt wird (siehe Modul-Docstring).

    filename/content sind optional und nur fuer den Vision-Fallback noetig:
    liefert die text-basierte Extraktion einen oder mehrere der Standard-
    felder (Name/Rolle/Telefon/PLZ) nicht, wird bei PDFs automatisch die
    erste Seite zusaetzlich per Vision ausgelesen (siehe
    _extract_fields_via_vision) - das faengt genau den Fall auf, in dem eine
    defekte Font-Kodierung im PDF den Text-Layer unbrauchbar macht. Ohne
    filename/content (z.B. in den Batch-Backfill-Skripten) faellt dieser
    Fallback einfach weg, keine Verhaltensaenderung dort."""
    raw = generate_text(
        system_prompt=_FIELD_EXTRACTION_SYSTEM_PROMPT,
        user_message=cv_text[:12000],
        # 1500 statt urspruenglich 750: berufliche_stationen (komplette
        # Stationshistorie statt nur der aktuellsten Position) und rollen/
        # current_employer_internal liefern deutlich mehr Output als die
        # bisherigen reinen Kurzfelder.
        max_tokens=1500,
        # timeout=25.0 (statt Standard 45.0): dieser Call kann bei PDFs von
        # einem zweiten, sequenziellen Vision-Fallback-Call gefolgt werden
        # (siehe unten) - beide zusammen muessen sicher unter dem App-
        # Platform-Gateway-Timeout bleiben, siehe Kommentar bei
        # _extract_fields_via_vision.
        timeout=25.0,
    )
    data = _parse_json_response(raw)
    # Defensiv: das Modell haelt sich fast immer an das Array-Schema, aber
    # ohne diese Normalisierung wuerde ein fehlendes/falsch typisiertes Feld
    # (z.B. null statt []) weiter unten beim Speichern (JSON-Spalte, erwartet
    # eine Liste) zu einem Fehler fuehren statt einfach als "nichts gefunden"
    # behandelt zu werden.
    if not isinstance(data.get("fachliche_schwerpunkte"), list):
        data["fachliche_schwerpunkte"] = []
    data["rollen"] = _normalize_rollen(data.get("rollen"))
    data["berufliche_stationen"] = _normalize_berufliche_stationen(data.get("berufliche_stationen"))

    agency_profile = is_agency_letterhead(cv_text)
    if agency_profile:
        for key in ("first_name", "last_name", "email", "postal_code", "city", "phone"):
            data[key] = None

    is_pdf = filename is not None and Path(filename).suffix.lower() == ".pdf"
    missing_standard_fields = any(not data.get(field) for field in _STANDARD_FIELDS_TO_VERIFY)
    if missing_standard_fields and not agency_profile and is_pdf and content is not None:
        try:
            vision_data = _extract_fields_via_vision(content)
        except Exception:
            # Der Vision-Fallback ist eine Zusatzchance, kein kritischer Pfad -
            # schlaegt er fehl (z.B. defektes PDF, API-Fehler), bleibt einfach
            # das Ergebnis der Text-Extraktion stehen statt den ganzen Request
            # scheitern zu lassen.
            logger.warning(
                "CV-Vision-Fallback fehlgeschlagen, behalte Text-Extraktion.", exc_info=True
            )
        else:
            for key, value in vision_data.items():
                if value and not data.get(key):
                    data[key] = value
            # vision_data durchlief die obige Normalisierung nicht - erneut
            # anwenden, damit ein von dort gemergter roher rollen-/
            # berufliche_stationen-Wert nicht ungeprueft durchrutscht.
            data["rollen"] = _normalize_rollen(data.get("rollen"))
            data["berufliche_stationen"] = _normalize_berufliche_stationen(
                data.get("berufliche_stationen")
            )
    return data
