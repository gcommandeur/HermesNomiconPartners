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

from cc_crm.core.errors import AIProviderError
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

NEBENTÄTIGKEITEN NICHT ALS "ZEITLICH LETZTE" STATION ZÄHLEN: steht eine
Position im CV erkennbar unter einer eigenen Überschrift wie "Praktika",
"Nebentätigkeiten", "Nebenjob" oder "Aushilfstätigkeit" (bzw. ist sie
inhaltlich klar als solche gekennzeichnet, z.B. Studentenjob/Aushilfe neben
Ausbildung/Studium), zählt sie NICHT als reguläre berufliche Station für die
Ableitung von "rollen" oder current_employer_internal - selbst wenn sie
zeitlich NACH der letzten regulären Berufserfahrung-Station liegt. Beispiel:
10/2016-06/2021 Wirtschaftsprüfungsassistent unter "BERUFSERFAHRUNG", danach
09/2021-08/2023 Speiselieferant unter "Praktika und Nebentätigkeiten" ->
rollen: ["pruefungsassistent"], current_employer_internal bezieht sich auf
die Wirtschaftsprüfungsgesellschaft - NICHT auf den Lieferdienst. Diese
Nebentätigkeiten trotzdem regulär in berufliche_stationen mit aufnehmen
(vollständige Historie), aber an ihrer tatsächlichen zeitlichen Position -
sie werden nur bei der "zeitlich letzte relevante Rolle"-Ableitung
übersprungen.

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
        #
        # Bekannter pypdf-Bug (bestaetigt anhand von 28 real betroffenen CVs):
        # bei Seiten mit rotierten Text-Elementen (z.B. quer gedrehte
        # Seitenrand-Vermerke) liefert "layout" fuer die GANZE Seite einen
        # leeren String, obwohl der Default-Modus denselben Text problemlos
        # findet. Seiten, die im Layout-Modus leer bleiben, bekommen daher pro
        # Seite einen Fallback auf den Default-Modus statt die ganze Seite als
        # "kein Text vorhanden" zu behandeln.
        pages_text: list[str] = []
        for page in reader.pages:
            layout_text = page.extract_text(extraction_mode="layout") or ""
            if layout_text.strip():
                pages_text.append(layout_text)
            else:
                pages_text.append(page.extract_text() or "")
        return "\n".join(pages_text)
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


_EMPTY_STRUCTURED_FIELDS: dict[str, Any] = {
    "first_name": None,
    "last_name": None,
    "email": None,
    "postal_code": None,
    "city": None,
    "phone": None,
    "job_title": None,
    "qualification": None,
    "ausbildung_titel": None,
    "fachliche_schwerpunkte": [],
    "rollen": [],
    "current_employer_internal": None,
    "berufliche_stationen": [],
}

# Nur fuer den regelbasierten Fallback (siehe _extract_contact_fields_via_regex)
# - bewusst konservativ: nur Felder, die sich ohne Sprachverstaendnis
# zuverlaessig per Muster erkennen lassen (E-Mail/Telefon/PLZ+Ort). Name
# NICHT per Regex raten (Risiko falscher Werte, z.B. aus einer Kanzlei-
# Kopfzeile) - "erfinde nichts" gilt auch hier, nicht nur fuer das LLM.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Bewusst " " statt "\s" innerhalb der Zeichenklasse (matcht sonst auch
# Zeilenumbrueche und "frisst" sich in die naechste Zeile, z.B. in eine
# direkt folgende PLZ) und eine Obergrenze fuer die Wiederholung, damit der
# Match nicht ueber die eigentliche Telefonnummer hinaus laeuft.
_PHONE_RE = re.compile(r"(?:\+49[\d ()/-]{5,17}\d|\b0[\d ()/-]{5,17}\d)")
_PLZ_CITY_RE = re.compile(
    r"\b(\d{5})\s+([A-ZÄÖÜ][a-zäöüß]+(?:[- ][A-ZÄÖÜ][a-zäöüß]+)*)"
)


def _extract_contact_fields_via_regex(cv_text: str) -> dict[str, Any]:
    """Kostenlose, rein regelbasierte Notfall-Extraktion - Fallback, wenn das
    LLM nicht erreichbar ist (z.B. API-Guthaben leer, siehe
    extract_candidate_fields). Liefert bewusst NUR die per Muster
    zuverlaessig erkennbaren Kontaktfelder (E-Mail/Telefon/PLZ+Ort) - Rolle/
    Qualifikation/fachliche Schwerpunkte/berufliche Stationen brauchen
    Sprachverstaendnis und bleiben leer, statt geraten zu werden. Ein
    Kandidat kann darauf trotzdem angelegt und die smarten Felder spaeter
    manuell oder per erneutem CV-Re-Parse (sobald wieder Guthaben vorhanden
    ist) ergaenzt werden."""
    result = dict(_EMPTY_STRUCTURED_FIELDS)

    email_match = _EMAIL_RE.search(cv_text)
    if email_match:
        result["email"] = email_match.group(0)

    phone_match = _PHONE_RE.search(cv_text)
    if phone_match:
        result["phone"] = phone_match.group(0).strip()

    plz_city_match = _PLZ_CITY_RE.search(cv_text)
    if plz_city_match:
        result["postal_code"] = plz_city_match.group(1)
        result["city"] = plz_city_match.group(2)

    return result


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
    Fallback einfach weg, keine Verhaltensaenderung dort.

    Schlaegt der LLM-Call selbst fehl (z.B. API-Guthaben leer, Netzwerk-
    Timeout, kaputte JSON-Antwort) wird NICHT die ganze Extraktion (und
    damit das Kandidat-anlegen-Formular) mit einem Fehler abgebrochen -
    Nutzer-Vorgabe: lieber ein Kandidat mit nur den per Regex erkennbaren
    Kontaktfeldern (E-Mail/Telefon/PLZ/Ort) als gar keiner. Die "smarten"
    Felder (Rolle/Qualifikation/Schwerpunkte/Stationen) bleiben in diesem
    Fall leer und koennen spaeter per erneutem CV-Re-Parse nachgeliefert
    werden, sobald wieder Guthaben vorhanden ist.

    Das Rueckgabe-Dict traegt IMMER den Schluessel "llm_fallback_used"
    (False im Erfolgsfall, True im Regex-Fallback-Pfad) - Aufrufer, die
    einen erfolgreichen LLM-Call von einem blossen Fallback-Ergebnis
    unterscheiden muessen (z.B. Batch-Backfill-Skripte mit Checkpoint/
    Resume, siehe scripts/backfill_cv_rollen_und_schwerpunkte.py), sollen
    sich auf dieses Flag stuetzen statt auf "smarte Felder sind leer" zu
    schliessen - ein echter LLM-Erfolg kann fuer ein bestimmtes CV genauso
    legitim leere smarte Felder liefern, wenn dort schlicht nichts zu
    erkennen war."""
    try:
        raw = generate_text(
            system_prompt=_FIELD_EXTRACTION_SYSTEM_PROMPT,
            user_message=cv_text[:12000],
            # 2500 statt urspruenglich 1500: bei Kandidaten mit langer
            # Stationshistorie (viele berufliche_stationen-Eintraege) reichte
            # 1500 gelegentlich nicht - das Modell wurde mitten in der JSON-
            # Antwort abgeschnitten (stop_reason "max_tokens"), wodurch die
            # abgeschnittene Antwort mit dem oeffnenden "```json" begann und
            # json.loads sofort bei Zeichen 0 crashte, statt sauber zu
            # parsen (live reproduziert und verifiziert: Kandidat #4330,
            # 8716 Input-Tokens, exakt 1500 Output-Tokens ausgeschoepft).
            # Landete bisher im selben Fallback-Pfad wie ein echter API-
            # Fehler, obwohl das Modell fast die komplette, gueltige Antwort
            # bereits geliefert hatte - unnoetiger Qualitaetsverlust.
            max_tokens=2500,
            # timeout=25.0 (statt Standard 45.0): dieser Call kann bei PDFs von
            # einem zweiten, sequenziellen Vision-Fallback-Call gefolgt werden
            # (siehe unten) - beide zusammen muessen sicher unter dem App-
            # Platform-Gateway-Timeout bleiben, siehe Kommentar bei
            # _extract_fields_via_vision.
            timeout=25.0,
        )
        data = _parse_json_response(raw)
    except (AIProviderError, ValueError):
        logger.warning(
            "CV-Extraktion per LLM fehlgeschlagen (z.B. API-Guthaben leer/Timeout) - "
            "falle auf regelbasierte Kontaktfeld-Extraktion zurueck.",
            exc_info=True,
        )
        fallback_data = _extract_contact_fields_via_regex(cv_text)
        # Derselbe Schutz wie unten fuer den LLM-Pfad: ein automatisch von
        # Commandeur selbst erzeugtes anonymes Profil (faelschlich als "CV"
        # hochgeladen) darf NIE die eigene Kanzlei-Adresse/Telefonnummer als
        # vermeintliche Kandidatendaten uebernehmen.
        if is_agency_letterhead(cv_text):
            for key in ("email", "postal_code", "city", "phone"):
                fallback_data[key] = None
        fallback_data["llm_fallback_used"] = True
        return fallback_data
    # Defensiv: das Modell haelt sich fast immer an das Array-Schema, aber
    # ohne diese Normalisierung wuerde ein fehlendes/falsch typisiertes Feld
    # (z.B. null statt []) weiter unten beim Speichern (JSON-Spalte, erwartet
    # eine Liste) zu einem Fehler fuehren statt einfach als "nichts gefunden"
    # behandelt zu werden.
    if not isinstance(data.get("fachliche_schwerpunkte"), list):
        data["fachliche_schwerpunkte"] = []
    data["rollen"] = _normalize_rollen(data.get("rollen"))
    data["berufliche_stationen"] = _normalize_berufliche_stationen(data.get("berufliche_stationen"))
    data["llm_fallback_used"] = False

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
