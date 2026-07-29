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
# Endpoint und backfill_cv_fields.py leiten sich alle hieraus ab, statt das
# Feld an mehreren Stellen einzeln aufzuzaehlen). Feld MUSS als gleichnamiges
# Attribut sowohl auf Candidate (models/candidate.py) als auch auf
# CvExtractionSuggestion (schemas/candidate.py) existieren. Freitext-/
# Analysefelder, die (noch) keine eigene Kandidaten-Spalte haben (z.B.
# erfahrungen_zusammenfassung, siehe Prompt unten), gehoeren NICHT hierher -
# die landen ausschliesslich in cv_extraction_raw (siehe
# CandidateService.auto_fill_from_cv) und stehen darueber trotzdem jeder
# kuenftigen Funktion zur Verfuegung, ganz ohne neue Spalte/Migration.
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
)

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

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
  "ausbildung_titel": "<Ausbildung/Weiterbildung, kurz, oder null>",
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
  " / " getrennt angeben.
- fachliche_schwerpunkte: anders als job_title/qualification aus dem GESAMTEN
  Lebenslauf (nicht nur der aktuellsten Position) - konkrete, inhaltlich
  greifbare fachliche Schwerpunkte/Fähigkeiten, z.B. Rechtsgebiete
  ("Umsatzsteuer", "M&A"), Branchenspezialisierung ("Automotive-Mandanten"),
  Fachsoftware ("DATEV", "SAP FI"). KEINE generischen Floskeln wie
  "Teamfähigkeit", "Kommunikationsstärke" oder "selbstständiges Arbeiten" -
  nur fachlich/inhaltlich verwertbare Stichpunkte, kurz gehalten (2-6 Wörter
  je Eintrag). Leeres Array, falls nichts Konkretes im Text erkennbar ist.
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

_LAST_ROLE_SYSTEM_PROMPT = """Du extrahierst die aktuellste/letzte berufliche Station aus einem
Lebenslauf-Text für ein Recruiting-CRM (Fokus Steuern/Wirtschaftsprüfung/Recht).

Gib AUSSCHLIESSLICH ein JSON-Objekt zurück (kein Markdown-Codeblock, keine
Erklärung davor/danach), mit exakt diesen Schlüsseln:
{
  "job_title": "<aktuellste/letzte Berufsbezeichnung, kurz, oder null>",
  "employer": "<Name des aktuellsten/letzten Arbeitgebers, oder null>",
  "qualification": "<Qualifikation/Berufsabschluss, kurz z.B. 'Steuerberater', oder null>",
  "ausbildung_titel": "<Ausbildung/Weiterbildung, kurz, oder null>"
}

REGELN:
- Nutze NUR Informationen, die explizit im Text stehen. Erfinde nichts.
- Falls ein Feld nicht sicher aus dem Text hervorgeht, setze null statt zu raten.
- Nur die aktuellste/letzte Position, nicht die gesamte Berufshistorie.
- employer: der Klarname des Arbeitgebers (wird intern gespeichert, nicht
  automatisch veröffentlicht) - falls der Text ein anonymisiertes
  Bewerberprofil einer Personalberatung ist (siehe Briefkopf), ist der
  Arbeitgeber dort ohnehin meist schon anonymisiert/generisch beschrieben;
  in diesem Fall diese generische Beschreibung übernehmen, keinen Namen erfinden."""


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
    text-basierte Extraktion, nur mit Bild statt Text als Eingabe."""
    image_base64 = _render_first_pdf_page_png_base64(content)
    raw = generate_text_with_image(
        system_prompt=_FIELD_EXTRACTION_SYSTEM_PROMPT,
        user_message="Lies die Felder aus dem Bild der ersten Lebenslauf-Seite aus.",
        image_base64=image_base64,
        max_tokens=750,
    )
    return _parse_json_response(raw)


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
        # 750 statt urspruenglich 400: fachliche_schwerpunkte (Liste) und
        # erfahrungen_zusammenfassung (Fliesstext) liefern deutlich mehr
        # Output als die anfaenglichen reinen Kurzfelder.
        max_tokens=750,
    )
    data = _parse_json_response(raw)
    # Defensiv: das Modell haelt sich fast immer an das Array-Schema, aber
    # ohne diese Normalisierung wuerde ein fehlendes/falsch typisiertes Feld
    # (z.B. null statt []) weiter unten beim Speichern (JSON-Spalte, erwartet
    # eine Liste) zu einem Fehler fuehren statt einfach als "nichts gefunden"
    # behandelt zu werden.
    if not isinstance(data.get("fachliche_schwerpunkte"), list):
        data["fachliche_schwerpunkte"] = []

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
    return data


def extract_last_role(cv_text: str) -> dict[str, Any]:
    """Fuer Punkt 4 (Batch-Backfill): nur Rolle/Arbeitgeber/Qualifikation/
    Ausbildung - keine Adress-/Kontaktfelder noetig, daher kein
    Agentur-Briefkopf-Ausschluss fuer diese Felder erforderlich."""
    raw = generate_text(
        system_prompt=_LAST_ROLE_SYSTEM_PROMPT,
        user_message=cv_text[:12000],
        max_tokens=400,
    )
    return _parse_json_response(raw)
