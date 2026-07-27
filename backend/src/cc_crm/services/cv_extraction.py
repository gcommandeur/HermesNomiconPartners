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

import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any

import docx
from pypdf import PdfReader

from cc_crm.integrations.ai.anthropic_client import generate_text

AGENCY_LETTERHEAD_MARKER = "Commandeur Consulting GmbH"

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
  "ausbildung_titel": "<Ausbildung/Weiterbildung, kurz, oder null>"
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


def extract_candidate_fields(cv_text: str) -> dict[str, Any]:
    """Fuer Punkt 2 (manueller Einzel-Upload): Name/E-Mail/PLZ/Ort/Telefon/
    Rolle/Qualifikation/Ausbildung. Alle personenbezogenen Felder werden
    zusaetzlich zur Prompt-Instruktion hart auf None gesetzt, wenn der
    Agentur-Briefkopf erkannt wird (siehe Modul-Docstring)."""
    raw = generate_text(
        system_prompt=_FIELD_EXTRACTION_SYSTEM_PROMPT,
        user_message=cv_text[:12000],
        max_tokens=400,
    )
    data = _parse_json_response(raw)
    if is_agency_letterhead(cv_text):
        for key in ("first_name", "last_name", "email", "postal_code", "city", "phone"):
            data[key] = None
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
