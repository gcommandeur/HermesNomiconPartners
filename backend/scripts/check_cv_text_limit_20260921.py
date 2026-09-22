"""Rein lesende Stichprobe: schneidet die 12.000-Zeichen-Grenze in
services/cv_extraction.py::extract_candidate_fields (cv_text[:12000]) bei
langen CVs berufliche Stationen ab?

Liest alle CV-Dokumente (document_type "cv", PDF/DOCX) aus der Datenbank und
dem Dokumentenspeicher, extrahiert den Text wie die Produktion
(extract_text_from_bytes) und gibt NUR Aggregatzahlen aus - keine Namen,
keine Inhalte. Es wird nichts geschrieben und kein LLM aufgerufen.

Gemessen wird:
- Laengenverteilung des extrahierten Texts (roh vs. ohne Whitespace - der
  pypdf-Layout-Modus fuellt Zeilen mit Leerzeichen auf, 12.000 rohe Zeichen
  sind deshalb deutlich weniger echter Inhalt)
- wie viele CVs ueber der Grenze liegen
- wie viele davon hinter der Grenze noch Stations-Muster enthalten
  (Zeitraeume wie "2015 - 2018", "05/2019 - heute", "seit 2020")
- wie viele CVs nach dem Zusammenfassen von Leerzeichen-Folgen noch ueber
  der Grenze lagen

Usage (von backend/, mit aktivierter venv):

    python scripts/check_cv_text_limit_20260921.py
"""

from __future__ import annotations

import re
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from cc_crm.core.config import get_settings  # noqa: E402
from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.operational import Document  # noqa: E402
from cc_crm.services.cv_extraction import extract_text_from_bytes  # noqa: E402


# Bewusst NICHT services.storage.read_document_bytes: ist in .env ein
# S3-Bucket konfiguriert (hier der Fall - Produktions-Zugangsdaten fuer
# Backfills), liest die normale Storage-Funktion IMMER von dort, selbst wenn
# lokale Kopien der Dateien vorliegen. In dieser Sandbox ist das S3-Ziel
# nicht erreichbar - jeder Aufruf haengt in der boto3-Retry-Logik (live
# beobachtet: 10+ Stunden fuer 1126 Dokumente, DNS-Fehler fuer
# fra1.digitaloceanspaces.com). Diese Stichprobe braucht nur lokal
# vorhandene Dateien und liest deshalb direkt vom Dokumentenordner.
def _read_local_document_bytes(storage_key: str) -> bytes:
    path = get_settings().resolved_documents_storage_dir / storage_key
    return path.read_bytes()

LIMIT = 12000

_MONTH_YEAR = r"(?:\d{1,2}[./]\s?)?(?:19|20)\d{2}"
_STATION_RE = re.compile(
    rf"{_MONTH_YEAR}\s*[-–—bis]+\s*(?:{_MONTH_YEAR}|heute|jetzt|aktuell|gegenwart|present)"
    r"|seit\s+(?:\d{1,2}[./]\s?)?(?:19|20)\d{2}",
    re.IGNORECASE,
)


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text)


def _percentile(values: list[int], pct: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * pct))]


def main() -> None:
    stats: Counter[str] = Counter()
    raw_lengths: list[int] = []
    dense_lengths: list[int] = []
    over_details: list[tuple[str, int, int, int]] = []

    with SessionLocal() as session:
        documents = list(session.scalars(select(Document).where(Document.document_type == "cv")))

    for document in documents:
        suffix = Path(document.filename).suffix.lower()
        if suffix not in (".pdf", ".docx"):
            stats["uebersprungen (kein PDF/DOCX)"] += 1
            continue
        try:
            text = extract_text_from_bytes(
                document.filename, _read_local_document_bytes(document.storage_key)
            )
        except Exception:  # noqa: BLE001 - Stichprobe, ein defektes Dokument darf nicht abbrechen
            stats["nicht lesbar"] += 1
            continue
        stats["ausgewertet"] += 1
        raw = len(text)
        dense = len(_collapse_whitespace(text))
        raw_lengths.append(raw)
        dense_lengths.append(dense)
        if dense > LIMIT:
            stats["nach Leerzeichen-Kompression noch ueber Grenze"] += 1
            dense_tail = _collapse_whitespace(text)[LIMIT:]
            if _STATION_RE.search(dense_tail):
                stats["  davon mit Stations-Mustern hinter der Grenze (komprimiert)"] += 1
                if "zeugnis" in dense_tail.lower():
                    stats["    davon Rest enthaelt 'Zeugnis' (evtl. angehaengte Zeugnisse)"] += 1
        if raw <= LIMIT:
            continue
        stats["roh ueber Grenze"] += 1
        head, tail = text[:LIMIT], text[LIMIT:]
        tail_has_content = len("".join(tail.split())) > 0
        stations_head = len(_STATION_RE.findall(head))
        stations_tail = len(_STATION_RE.findall(tail))
        if tail_has_content:
            stats["  davon mit Inhalt hinter der Grenze"] += 1
        if stations_tail:
            stats["  davon mit Stations-Mustern hinter der Grenze"] += 1
            if "zeugnis" in tail.lower():
                stats["    davon Rest enthaelt 'Zeugnis' (evtl. angehaengte Zeugnisse)"] += 1
        over_details.append((str(document.id), raw, stations_head, stations_tail))

    print(f"CV-Dokumente in der DB: {len(documents)}")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    if raw_lengths:
        print()
        print(
            "Textlaenge roh (Zeichen):   "
            f"Median {int(statistics.median(raw_lengths))}, "
            f"P90 {_percentile(raw_lengths, 0.90)}, P99 {_percentile(raw_lengths, 0.99)}, "
            f"Max {max(raw_lengths)}"
        )
        print(
            "Textlaenge ohne Padding:    "
            f"Median {int(statistics.median(dense_lengths))}, "
            f"P90 {_percentile(dense_lengths, 0.90)}, P99 {_percentile(dense_lengths, 0.99)}, "
            f"Max {max(dense_lengths)}"
        )
    if over_details:
        print()
        print("Betroffene CVs (Dokument-ID, roh, Stationen vor Grenze, Stationen HINTER Grenze):")
        for doc_id, raw, head, tail in sorted(over_details, key=lambda row: -row[3])[:15]:
            print(f"  {doc_id}  {raw:>6}  {head:>3}  {tail:>3}")


if __name__ == "__main__":
    main()
