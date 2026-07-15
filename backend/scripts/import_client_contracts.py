"""Importiert echte Kanzlei-Kunden aus dem "Verträge"-Ordner (unterschriebene/
gesendete Vermittlungsverträge) und ersetzt damit die einmalige Platzhalter-
Testkanzlei ("TEST - Steuerkanzlei München") aus dem ersten Durchlauf.

WICHTIG: Dieses Skript NACH import_master_candidates.py ausführen (das löscht
per wipe_test_data() bereits alle Kanzlei-Testdaten) - dieses Skript hier löscht
NICHTS, es legt nur neu an. Bei mehrfachem Ausführen entstehen Duplikate.

Voraussetzung:
    cd backend
    .\\.venv\\Scripts\\pip.exe install -e ".[dev]"   (pypdf neu in pyproject.toml)
    CC_CRM_ANTHROPIC_API_KEY muss konfiguriert sein (wie bei Phase 2/4)

Ausführen:
    .\\.venv\\Scripts\\python.exe scripts\\import_client_contracts.py

Was passiert:
1. Der Verträge-Ordner enthält pro Kanzlei meist 2 Dateien (.docx + .pdf,
   identischer Inhalt) und manchmal mehrere Varianten (z.B. "_Profil 4046"-
   Suffixe für unterschiedliche Platzierungen). Dateien werden anhand des
   Dateinamens (Präfix/Suffix-Rauschen entfernt) zu Gruppen zusammengefasst.
2. Pro Gruppe wird der Text ALLER Dateien der Gruppe zusammengeführt (nicht nur
   einer Repräsentativ-Datei) - manche pdf-Fassungen (z.B. tatsächlich versendete
   Briefe) enthalten eine Anschrift, die die docx-Vorlage nicht hat.
3. Ein LLM-Call pro Gruppe extrahiert aus dem zusammengeführten Vertragstext: den echten rechtlichen
   Firmennamen (Verträge nennen z.B. "aktax" im Dateinamen, aber "Arnold &
   Partner Wirtschaftsprüfer Steuerberater mbB" im Vertragstext - das ist die
   Information, die wir wirklich brauchen), Anschrift (falls vorhanden -
   viele Verträge enthalten keine), Honorarsatz, Honorar-Basis (übliche
   Vermittlungsverträge: % vom Bruttojahreszielgehalt; einzelne abweichende
   Verträge, z.B. Kanzleivermittlung/M&A-Nachweis: % vom Transaktionswert),
   Vertragsdatum, und eine kurze Notiz zu Besonderheiten.
   Resilient: schlägt die Extraktion fehl, wird ein sinnvoller Fallback
   (Dateiname als Firmenname, 27% Standard-Honorar) verwendet statt
   abzubrechen - IMMER klar in commercial_notes vermerkt, damit erkennbar
   bleibt, was automatisch geraten wurde.
4. ZWEITER Durchlauf: Gruppen, deren extrahierter rechtlicher Firmenname
   übereinstimmt (z.B. Dateiname "_2512" und "_afileon" extrahieren beide
   "Afileon GmbH"; "linngoppold" und "Linn Goppold Treuhand GmbH" extrahieren
   beide denselben Namen), werden zu EINER Kanzlei zusammengeführt - alle
   zugehörigen Dateien werden dieser einen Kanzlei als Dokumente angehängt.
   Das verhindert Duplikate, die bei reiner Dateinamens-Gruppierung entstehen
   würden.
5. Legt pro zusammengeführter Gruppe eine ClientCompany an (status=active,
   da bereits unterschriebener Vertrag) + hängt alle Dateien der Gruppe als
   Document (document_type="vertrag") an.
6. Gibt eine Zusammenfassung aus, inkl. aller Fälle, in denen die
   LLM-Extraktion fehlgeschlagen ist / der Fallback griff - zur manuellen
   Kontrolle.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import docx  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from cc_crm.core.errors import AIProviderError  # noqa: E402
from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.integrations.ai.anthropic_client import generate_text  # noqa: E402
from cc_crm.models.enums import ClientStatus, HonorarStufe  # noqa: E402
from cc_crm.schemas.client_company import ClientCompanyCreate  # noqa: E402
from cc_crm.schemas.operational import DocumentCreate  # noqa: E402
from cc_crm.services.clients import ClientCompanyService  # noqa: E402
from cc_crm.services.operational import DocumentService  # noqa: E402
from cc_crm.services.storage import save_document_bytes  # noqa: E402

VERTRAEGE_FOLDER = Path(r"C:\Users\comma\OneDrive - Commandeur Consulting GmbH\Desktop\Verträge")

PREFIX_RE = re.compile(
    r"^(Kanzleivermittlungsvertrag_CC[_ ]|Vermittlungsvertrag_CC[_ ])", re.IGNORECASE
)
SUFFIX_NOISE_RE = re.compile(
    r"(_Profil[ _]?\d+.*|_\d{8}_signed.*\(\d+\)|_\d{8}_signed.*|\s*-\s*Kopie.*|\(\d+\).*)$",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """Du liest einen Vermittlungsvertrag / Kanzleivermittlungsauftrag /
AGB-Rahmenvertrag zwischen der Commandeur Consulting GmbH (Personalberatung)
und einer Steuer-/Wirtschaftsprüfungs-/Rechtsanwaltskanzlei oder einem
Unternehmen. Extrahiere die folgenden Felder aus dem Vertragstext.

Gib AUSSCHLIESSLICH ein JSON-Objekt zurück, keine Erklärung, kein Markdown,
kein Codeblock - nur das rohe JSON.

Felder (null, wenn nicht im Text vorhanden):
{
  "legal_name": string,               // voller rechtlicher Name des Vertragspartners
                                       // (z.B. aus "im Namen von X" oder "Auftraggeber: X"),
                                       // NICHT der Dateiname/Spitzname
  "street": string | null,
  "postal_code": string | null,
  "city": string | null,
  "fee_percentage": number | null,    // reine Zahl, z.B. 27 oder 30 oder 5
  "fee_basis": string | null,         // kurz, z.B. "Bruttojahreszielgehalt" oder "Transaktionswert"
  "contract_date": string | null,     // wie im Text, z.B. "20.01.2026"
  "special_notes": string | null      // 1 kurzer Satz zu Besonderheiten/Abweichungen
                                       // vom Standard-Personalvermittlungsvertrag (27% vom
                                       // Bruttojahreszielgehalt), sonst null
}

Regeln:
- Erfinde nichts. Kein erkennbares Feld -> null.
- "legal_name" ist das wichtigste Feld - suche gezielt nach der vollständigen
  Firmierung des Vertragspartners (oft nahe "im Namen von", "Auftraggeber:",
  oder direkt in einem Adressblock).
"""

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(raw: str) -> str:
    fenced = _JSON_FENCE.search(raw)
    return fenced.group(1) if fenced else raw.strip()


def normalize_key(stem: str) -> str:
    stem = PREFIX_RE.sub("", stem)
    stem = SUFFIX_NOISE_RE.sub("", stem)
    stem = re.sub(r"\s+", " ", stem).strip().rstrip("_").strip()
    return stem.casefold()


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        document = docx.Document(str(path))
        return "\n".join(p.text for p in document.paragraphs if p.text.strip())
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def fallback_name_from_key(key: str) -> str:
    return key.replace("_", " ").strip().title()


def honorar_stufe_for(percentage: Decimal | None) -> HonorarStufe:
    if percentage is None:
        return HonorarStufe.STANDARD
    if percentage == 27:
        return HonorarStufe.STANDARD
    if percentage == 25:
        return HonorarStufe.NACHLASS_1
    if percentage == 23:
        return HonorarStufe.NACHLASS_2
    return HonorarStufe.INDIVIDUELL


def parse_percentage(raw: object) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def main() -> None:
    if not VERTRAEGE_FOLDER.is_dir():
        raise SystemExit(f"Verträge-Ordner nicht gefunden: {VERTRAEGE_FOLDER}")

    files = [f for f in sorted(VERTRAEGE_FOLDER.iterdir()) if f.suffix.lower() in (".docx", ".pdf")]
    filename_groups: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        filename_groups[normalize_key(f.stem)].append(f)
    print(f"Dateien gefunden: {len(files)}, Dateinamens-Gruppen: {len(filename_groups)}")

    # Pro Dateinamens-Gruppe: Text ALLER Dateien der Gruppe zusammenführen (nicht
    # nur einer Repräsentativ-Datei) und in EINEM LLM-Call extrahieren. Grund:
    # docx- und pdf-Variante desselben Vertrags haben nicht immer denselben
    # Informationsgehalt - manche pdf-Fassungen (z.B. tatsächlich versendete/
    # gescannte Briefe) enthalten eine Anschrift, die die docx-Vorlage nicht hat
    # (beobachtet bei Linn Goppold Treuhand GmbH). Mit nur einer Datei pro Gruppe
    # gingen dadurch Adressdaten verloren, obwohl sie im Ordner vorhanden waren.
    extracted: dict[str, dict[str, object]] = {}
    fallback_used: list[str] = []
    for key, group_files in filename_groups.items():
        try:
            combined_text = "\n\n=====\n\n".join(extract_text(f) for f in group_files)
            raw = generate_text(
                system_prompt=SYSTEM_PROMPT, user_message=combined_text[:10000], max_tokens=400
            )
            data = json.loads(_extract_json(raw))
            if not isinstance(data, dict) or not data.get("legal_name"):
                raise ValueError("LLM lieferte kein verwertbares legal_name")
        except (AIProviderError, ValueError, TypeError, json.JSONDecodeError) as exc:
            data = {
                "legal_name": fallback_name_from_key(key),
                "street": None,
                "postal_code": None,
                "city": None,
                "fee_percentage": 27,
                "fee_basis": None,
                "contract_date": None,
                "special_notes": (
                    f"Automatische Extraktion fehlgeschlagen ({exc}) - "
                    "Fallback auf Dateinamen, bitte prüfen."
                ),
            }
            fallback_used.append(key)
        extracted[key] = data

    # Nach extrahiertem legal_name zusammenführen (löst z.B. "_2512"/"_afileon"
    # oder "linngoppold"/"linn goppold treuhand gmbh" als EINE Kanzlei auf).
    merged: dict[str, dict[str, object]] = {}
    merged_files: dict[str, list[Path]] = defaultdict(list)
    for key, data in extracted.items():
        name_key = str(data["legal_name"]).strip().casefold()
        if name_key not in merged:
            merged[name_key] = data
        merged_files[name_key].extend(filename_groups[key])

    print(f"Nach Zusammenführung gleicher Firmennamen: {len(merged)} echte Kanzleien")

    # Verifizierte Ergänzungen für Kanzleien, die als Netzwerk/Marke mit
    # mehreren eigenständigen Standorten auftreten (Verträge nennen oft nur die
    # Marke, nicht den konkreten Standort). Adresse = öffentlich recherchierter
    # Hauptsitz/bekannter Standort - bei Bedarf im CRM auf den tatsächlich
    # relevanten Standort anpassen oder weitere Standorte separat anlegen
    # (dafür existiert das Feld "kanzleigruppe" - mehrere ClientCompany-Zeilen
    # können denselben Gruppennamen tragen, z.B. "ECOVIS RTS" und ein anderer
    # Standort beide mit kanzleigruppe="ECOVIS").
    KNOWN_GROUP_OVERRIDES: dict[str, dict[str, str]] = {
        "afileon": {
            "kanzleigruppe": "Afileon",
            "street": "Raiffeisenallee 9",
            "postal_code": "82041",
            "city": "Oberhaching",
            "note": (
                "Hauptsitz (Afileon Audit GmbH) - recherchiert, nicht aus Vertrag extrahiert. "
                "Afileon ist ein Verbundmodell mit mehreren Standorten - bei Bedarf "
                "spezifischen Standort ergänzen."
            ),
        },
        "ecovis": {
            "kanzleigruppe": "ECOVIS",
            "street": "Daimlerstraße 127",
            "postal_code": "70372",
            "city": "Stuttgart",
            "note": (
                "ECOVIS RTS Hauptsitz Stuttgart - recherchiert, nicht aus Vertrag extrahiert. "
                "ECOVIS ist ein großes Netzwerk mit vielen eigenständigen "
                "Untergruppen/Standorten (u.a. ECOVIS RTS mit ca. 70 Standorten in "
                "Baden-Württemberg) - bitte den tatsächlich relevanten Standort/die "
                "Untergruppe prüfen und im Namen/kanzleigruppe präzisieren."
            ),
        },
    }
    for name_key, data in merged.items():
        for fragment, override in KNOWN_GROUP_OVERRIDES.items():
            if fragment in name_key:
                data.setdefault("kanzleigruppe", override["kanzleigruppe"])
                if not data.get("street"):
                    data["street"] = override["street"]
                if not data.get("postal_code"):
                    data["postal_code"] = override["postal_code"]
                if not data.get("city"):
                    data["city"] = override["city"]
                existing_notes = data.get("special_notes") or ""
                data["special_notes"] = (existing_notes + " " if existing_notes else "") + override[
                    "note"
                ]
                break

    session = SessionLocal()
    try:
        client_service = ClientCompanyService(session)
        document_service = DocumentService(session)

        created = 0
        documents_attached = 0
        failed_groups: list[tuple[str, str]] = []

        for name_key, data in merged.items():
            try:
                fee_percentage = parse_percentage(data.get("fee_percentage")) or Decimal("27.00")
                notes_parts = [
                    "Automatisch aus Vermittlungsvertrag importiert (Verträge-Ordner) - "
                    "bei Bedarf prüfen/ergänzen."
                ]
                if data.get("contract_date"):
                    notes_parts.append(f"Vertragsdatum: {data['contract_date']}")
                if data.get("fee_basis"):
                    notes_parts.append(f"Honorar-Basis: {data['fee_basis']}")
                if data.get("special_notes"):
                    notes_parts.append(f"Besonderheit: {data['special_notes']}")

                client = client_service.create(
                    ClientCompanyCreate(
                        name=str(data["legal_name"])[:240],
                        kanzleigruppe=data.get("kanzleigruppe"),
                        status=ClientStatus.ACTIVE,
                        street=data.get("street"),
                        postal_code=data.get("postal_code"),
                        city=data.get("city"),
                        fee_percentage=fee_percentage,
                        honorar_stufe=honorar_stufe_for(fee_percentage),
                        commercial_notes="\n".join(notes_parts),
                    )
                )
                created += 1

                for file_path in merged_files[name_key]:
                    content = file_path.read_bytes()
                    storage_key = save_document_bytes(
                        owner_type="client",
                        owner_id=client.id,
                        filename=file_path.name,
                        content=content,
                    )
                    document_service.create(
                        DocumentCreate(
                            owner_type="client",
                            owner_id=client.id,
                            document_type="vertrag",
                            filename=file_path.name,
                            storage_key=storage_key,
                            content_type=(
                                "application/pdf"
                                if file_path.suffix.lower() == ".pdf"
                                else (
                                    "application/vnd.openxmlformats-officedocument"
                                    ".wordprocessingml.document"
                                )
                            ),
                            size_bytes=len(content),
                            uploaded_by="import_client_contracts.py",
                        )
                    )
                    documents_attached += 1
            except Exception as exc:  # noqa: BLE001 - eine fehlerhafte Gruppe darf den Rest nicht stoppen
                failed_groups.append((str(data.get("legal_name", name_key)), str(exc)))
                session.rollback()
                continue

        print("---")
        print(f"Echte Kanzleien angelegt: {created}")
        print(f"Vertragsdokumente angehängt: {documents_attached}")
        print(
            f"Fallback (Extraktion fehlgeschlagen, Dateiname als Name verwendet): "
            f"{len(fallback_used)}"
        )
        for key in fallback_used:
            print(f"  - {key}")
        if failed_groups:
            print(f"Fehlgeschlagen beim Anlegen (nicht importiert): {len(failed_groups)}")
            for name, message in failed_groups:
                print(f"  - {name}: {message}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
