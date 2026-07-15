"""Realer Master-Import: ersetzt ALLE Test-/Platzhalterdaten (inkl. des
ersten Bullhorn-Notes-only-Durchlaufs aus import_bullhorn_notes.py) durch die
2675 echten Kandidaten aus CVs_master_updated.csv und hängt die passenden
CV-Dateien aus dem CVs-Ordner als Dokumente an.

Warum dieses Skript den ersten Durchlauf ersetzt: import_bullhorn_notes.py
konnte nur 308 Kandidaten aus einem reinen Notizen-Export rekonstruieren
(keine E-Mail/Telefon/Status/Herkunft). CVs_master_updated.csv ist die
tatsächliche, vollständige Kandidatenliste (2675 Zeilen, echte Kontaktdaten,
Herkunft, CV-Dateiname). Die 308 Bullhorn-Notizen werden NICHT verworfen,
sondern in einem zweiten Skript (merge_bullhorn_notes.py) per Namens-Match als
Timeline-Einträge an die hier importierten echten Kandidaten angehängt.

Voraussetzungen:
    cd backend
    .\\.venv\\Scripts\\pip.exe install -e ".[dev]"   (python-multipart, pypdf neu)
    .\\.venv\\Scripts\\python.exe -m alembic upgrade head
    Backend-Server stoppen (SQLite-Dateizugriff)

Ausführen:
    .\\.venv\\Scripts\\python.exe scripts\\import_master_candidates.py

Was passiert:
1. wipe_test_data() - löscht ALLE Zeilen in ALLEN Business-Tabellen (Kandidaten,
   Kanzleien, Aktivitäten, Aufgaben, Dokumente, etc.), außer den Auth-Tabellen.
   Das entfernt auch die 308 Notizen-Kandidaten + die Platzhalter-Testkanzlei/
   -Teststelle aus dem vorigen Durchlauf.
2. Liest CVs_master_updated.csv (2675 Zeilen) und legt pro Zeile einen
   Candidate an:
   - candidate_number = CSV-Spalte "id" (192-4052) - das ist exakt dasselbe
     Nummernschema wie in den echten anonymisierten Profilen ("Nr. 4046-4052"),
     deshalb wurde _LEGACY_CANDIDATE_NUMBER_FLOOR in services/candidates.py
     genau auf 4052 gesetzt: neue, manuell angelegte Kandidaten bekommen ab
     sofort automatisch 4053, 4054, ... - nahtloser Anschluss.
   - Status: "DNU" -> blocked, sonst -> active
   - E-Mail: bevorzugt "Personal Email", sonst "Work Email"; wird validiert
     (Format-Check) - ungültige/leere E-Mails werden NICHT geraten, sondern
     weggelassen (Feld bleibt leer).
   - Telefon: bevorzugt "Mobile Phone", sonst "Work Phone".
   - freitext_notizen: "General Comments" + (bei Match_Konfidenz "low-review")
     ein Hinweis-Flag, wie vom Nutzer gewünscht ("normal importieren, aber
     intern markieren") + Herkunft/Quelle zur Nachvollziehbarkeit.
   - Vor-/Nachname: ca. 187 Zeilen der Quelle haben zwei Namensteile ohne
     Leerzeichen zusammengeschrieben (z.B. "AlenaDracke" statt "Alena Dracke"),
     weil die CSV ursprünglich aus CV-Dateinamen rekonstruiert wurde. Wird
     automatisch an der Kleinbuchstabe->Großbuchstabe-Grenze mit Leerzeichen
     korrigiert (siehe fix_smashed_name()) und zusätzlich in freitext_notizen
     markiert, da bei einigen Zeilen sogar Firmenname/Ort mit im Namensfeld
     gelandet ist - bitte stichprobenartig im CRM gegenprüfen.
3. Für jede Zeile mit gesetzter "CV_Datei"-Spalte: sucht die Datei im
   CVs-Ordner, kopiert die Bytes in den App-eigenen Dokumentenspeicher
   (services/storage.py), legt ein Document an (document_type="cv") und setzt
   candidate.cv_available = True.
4. Gibt eine Zusammenfassung aus.

Sicherheit: Dieses Skript ist NICHT gefahrlos wiederholt ausführbar (es löscht
vorher alles) - nur einmal laufen lassen. Nach einem missglückten Lauf: DB aus
Backup wiederherstellen oder Migration+Skript erneut von vorn.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models import Base, Candidate  # noqa: E402
from cc_crm.models.enums import CandidateStatus  # noqa: E402
from cc_crm.schemas.candidate import CandidateCreate, CandidateUpdate  # noqa: E402
from cc_crm.schemas.operational import DocumentCreate  # noqa: E402
from cc_crm.services.candidates import CandidateService  # noqa: E402
from cc_crm.services.operational import DocumentService  # noqa: E402
from cc_crm.services.storage import save_document_bytes  # noqa: E402

# Importing cc_crm.models (above) registers ALL model classes on Base.metadata,
# which wipe_test_data() below relies on for topologically-sorted deletion.

CSV_PATH = Path(
    r"C:\Users\comma\OneDrive - Commandeur Consulting GmbH\Desktop\CVs_master_updated.csv"
)
CV_FOLDER = Path(r"C:\Users\comma\OneDrive - Commandeur Consulting GmbH\Desktop\CVs")

PRESERVED_TABLES = {"users", "auth_sessions", "api_keys"}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Einige Zeilen der Quell-CSV wurden ursprünglich aus CV-Dateinamen rekonstruiert
# und haben dabei Wörter wie "Resume"/"Bewerbung" im Namen behalten (z.B. Vorname
# "Ekrem", Nachname "ErgunResume" - der Dateiname war "ErgunResume_Ekrem.pdf").
# Wird NICHT automatisch "repariert" (zu unsicher zu raten, was der echte Name
# ist) - wird aber erkannt und in freitext_notizen markiert, damit der Nutzer es
# im CRM (jetzt mit editierbaren Feldern) gezielt findet und von Hand korrigiert.
_SUSPICIOUS_NAME_RE = re.compile(r"resume|lebenslauf|bewerbung|profil|anschreiben", re.IGNORECASE)

# Häufigerer Fehler in derselben Quelle (~187 von 2675 Zeilen): zwei Namensteile
# ohne Leerzeichen zusammengeschrieben, weil die CSV ursprünglich aus
# CV-Dateinamen rekonstruiert wurde (z.B. Nachname "AlenaDracke" statt
# "Alena Dracke", "AlexanderHeinz" statt "Alexander Heinz"). Wird an der
# Kleinbuchstabe->Großbuchstabe-Grenze automatisch mit Leerzeichen repariert -
# eine rein mechanische Formatkorrektur (kein Raten, WELCHER Teil Vor-/Nachname
# ist), trotzdem in freitext_notizen markiert, da bei manchen Zeilen sogar der
# Firmenname/Ort mit im Nachnamen-Feld gelandet ist (das kann diese Korrektur
# nicht erkennen) - bitte stichprobenartig im CRM gegenprüfen.
_CAMEL_BOUNDARY_RE = re.compile(r"([a-zäöüßé])([A-ZÄÖÜ])")
_NO_SPLIT_PREFIX_RE = re.compile(r"^(Mc|Mac|O')(?=[A-ZÄÖÜ])")


def fix_smashed_name(value: str) -> tuple[str, bool]:
    """Fügt an Kleinbuchstabe->Großbuchstabe-Grenzen ein Leerzeichen ein
    (z.B. "AlenaDracke" -> "Alena Dracke"), außer bei Mc-/Mac-/O'-Präfixen
    (z.B. "McCray" bleibt "McCray"). Gibt (korrigierter_wert, wurde_geaendert)
    zurück."""
    if not value:
        return value, False
    prefix_match = _NO_SPLIT_PREFIX_RE.match(value)
    prefix, rest = (
        (value[: prefix_match.end()], value[prefix_match.end() :]) if prefix_match else ("", value)
    )
    fixed_rest = _CAMEL_BOUNDARY_RE.sub(r"\1 \2", rest)
    fixed = prefix + fixed_rest
    return fixed, fixed != value


_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".rtf": "application/rtf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def wipe_test_data(session) -> None:
    """Identisch zu import_bullhorn_notes.py::wipe_test_data - löscht alle
    Business-Tabellen in FK-sicherer Reihenfolge, behält nur Auth-Tabellen."""
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in PRESERVED_TABLES:
            continue
        session.execute(table.delete())
    session.commit()


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def valid_email(value: str | None) -> str | None:
    value = clean(value)
    if value and _EMAIL_RE.match(value):
        return value
    return None


def load_rows() -> list[dict[str, str]]:
    with open(CSV_PATH, encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def build_freitext_notizen(row: dict[str, str], *, name_was_fixed: bool = False) -> str | None:
    parts: list[str] = []
    comments = clean(row.get("General Comments"))
    if comments:
        parts.append(comments)

    herkunft = clean(row.get("Herkunft"))
    quelle = clean(row.get("Source"))
    provenance_bits = [bit for bit in (herkunft, quelle) if bit]
    if provenance_bits:
        parts.append("Herkunft: " + " / ".join(provenance_bits))

    konfidenz = clean(row.get("Match_Konfidenz"))
    if konfidenz and konfidenz.lower() == "low-review":
        parts.append(
            "⚠ INTERN: Match_Konfidenz=low-review beim CV-Abgleich - Angaben vor "
            "Kontaktaufnahme stichprobenartig gegenprüfen."
        )

    first_name = clean(row.get("First Name")) or ""
    last_name = clean(row.get("Surname")) or ""
    if _SUSPICIOUS_NAME_RE.search(first_name) or _SUSPICIOUS_NAME_RE.search(last_name):
        parts.append(
            "⚠ INTERN: Name wirkt aus einem CV-Dateinamen rekonstruiert (enthält "
            'z.B. "Resume"/"Bewerbung") - bitte Vor-/Nachname von Hand prüfen '
            "und korrigieren."
        )
    if name_was_fixed:
        parts.append(
            "⚠ INTERN: Vor-/Nachname wurde automatisch mit Leerzeichen korrigiert "
            '(ursprünglich ohne Leerzeichen zusammengeschrieben, z.B. "AlenaDracke" '
            '-> "Alena Dracke") - bitte kurz gegenprüfen, ob die Trennung stimmt '
            "und kein Firmenname/Ort mit im Namensfeld gelandet ist."
        )

    current_company = clean(row.get("Current Company"))
    if current_company:
        parts.append(f"Aktuelles Unternehmen (Quelldaten): {current_company}")

    return "\n\n".join(parts) if parts else None


def attach_cv(session, candidate: Candidate, cv_filename: str) -> bool:
    source_path = CV_FOLDER / cv_filename
    if not source_path.is_file():
        return False
    content = source_path.read_bytes()
    storage_key = save_document_bytes(
        owner_type="candidate",
        owner_id=candidate.id,
        filename=cv_filename,
        content=content,
    )
    DocumentService(session).create(
        DocumentCreate(
            owner_type="candidate",
            owner_id=candidate.id,
            document_type="cv",
            filename=cv_filename,
            storage_key=storage_key,
            content_type=_CONTENT_TYPES.get(source_path.suffix.lower()),
            size_bytes=len(content),
            uploaded_by="import_master_candidates.py",
        )
    )
    return True


def main() -> None:
    if not CSV_PATH.is_file():
        raise SystemExit(f"CSV nicht gefunden: {CSV_PATH}")
    if not CV_FOLDER.is_dir():
        raise SystemExit(f"CV-Ordner nicht gefunden: {CV_FOLDER}")

    rows = load_rows()
    print(f"Gelesene Zeilen: {len(rows)}")

    session = SessionLocal()
    try:
        wipe_test_data(session)
        candidate_service = CandidateService(session)

        created = 0
        emails_kept = 0
        emails_dropped = 0
        cv_attached = 0
        cv_missing = 0
        low_review = 0
        skipped_no_name = 0
        names_fixed = 0
        failed_rows: list[tuple[str, str]] = []  # (csv id, Fehlermeldung)

        for row in rows:
            row_id = clean(row.get("id")) or "?"
            first_name = clean(row.get("First Name"))
            last_name = clean(row.get("Surname"))
            if not first_name or not last_name:
                skipped_no_name += 1
                continue

            first_name, first_fixed = fix_smashed_name(first_name)
            last_name, last_fixed = fix_smashed_name(last_name)
            name_was_fixed = first_fixed or last_fixed
            if name_was_fixed:
                names_fixed += 1

            # Jede Zeile einzeln absichern: eine einzelne fehlerhafte Zeile (z.B.
            # eine E-Mail, die zwar unser Regex, aber nicht Pydantics strengere
            # EmailStr-Prüfung besteht) darf NICHT den gesamten Import abbrechen -
            # das war der Bug, der beim ersten Lauf zu fehlenden Kandidaten führte
            # (das Skript stoppte stillschweigend bei der ersten Ausnahme).
            try:
                raw_email = row.get("Personal Email") or row.get("Work Email")
                email = valid_email(raw_email)

                status_raw = clean(row.get("Status")) or ""
                status = (
                    CandidateStatus.BLOCKED
                    if status_raw.upper() == "DNU"
                    else CandidateStatus.ACTIVE
                )

                candidate = candidate_service.create(
                    CandidateCreate(
                        candidate_number=clean(row.get("id")),
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        phone=clean(row.get("Mobile Phone")) or clean(row.get("Work Phone")),
                        job_title=clean(row.get("Current Job Title")),
                        postal_code=clean(row.get("Post Code")),
                        city=clean(row.get("City")),
                        salary_expectation=clean(row.get("Desired Annual Salary")),
                        status=status,
                        freitext_notizen=build_freitext_notizen(row, name_was_fixed=name_was_fixed),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - bewusst breit, siehe Kommentar oben
                failed_rows.append((row_id, str(exc)))
                session.rollback()
                continue

            if clean(raw_email):
                if email:
                    emails_kept += 1
                else:
                    emails_dropped += 1
            konfidenz = clean(row.get("Match_Konfidenz"))
            if konfidenz and konfidenz.lower() == "low-review":
                low_review += 1

            created += 1

            cv_filename = clean(row.get("CV_Datei"))
            if cv_filename:
                try:
                    if attach_cv(session, candidate, cv_filename):
                        candidate_service.update(candidate.id, CandidateUpdate(cv_available=True))
                        cv_attached += 1
                    else:
                        cv_missing += 1
                except Exception as exc:  # noqa: BLE001
                    failed_rows.append((f"{row_id} (CV-Anhang)", str(exc)))
                    session.rollback()

            if created % 250 == 0:
                print(f"  ... {created}/{len(rows)} importiert")

        print("---")
        print(f"Kandidaten angelegt: {created}")
        print(f"Übersprungen (kein Name): {skipped_no_name}")
        print(f"Fehlgeschlagen (siehe Liste unten): {len(failed_rows)}")
        print(f"E-Mail übernommen: {emails_kept}")
        print(f"E-Mail verworfen (ungültiges Format): {emails_dropped}")
        print(f"CVs angehängt: {cv_attached}")
        print(f"CVs referenziert, aber Datei nicht gefunden: {cv_missing}")
        print(f"Intern markiert (Match_Konfidenz=low-review): {low_review}")
        print(f"Name automatisch mit Leerzeichen korrigiert (zusammengeschrieben): {names_fixed}")
        if failed_rows:
            print("---")
            print(
                "Fehlgeschlagene Zeilen (CSV-id: Fehlermeldung) - bitte manuell prüfen/nachtragen:"
            )
            for csv_id, message in failed_rows:
                print(f"  - {csv_id}: {message}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
