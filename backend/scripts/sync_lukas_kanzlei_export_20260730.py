"""Synchronisiert den Lukas-Mail-Abgleich (Gmail-Label "Lukas_Export") mit dem
CRM - Kanzlei-Korrekturen an Bestandsdaten + 37 neue Kanzleien/Kontakte.

WICHTIG zur Rollenteilung: der inhaltliche Datenabgleich (welche Kanzlei
korrigiert wird, welche blockiert wird, welche neuen Kontakte es gibt) ist
bereits extern geprueft und final - dieses Skript trifft KEINE eigenen
inhaltlichen Entscheidungen, es synchronisiert nur.

Sicherheits-Verhalten (Nutzer-Vorgabe): die IDs fuer Punkt 1/2 stammen aus
einem Export, dessen Aktualitaet zum Ausfuehrungszeitpunkt nicht zweifelsfrei
feststand - deshalb wird der aktuelle Stand jedes zu AKTUALISIERENDEN
Datensatzes unmittelbar vor dem Schreiben live per ID abgerufen (nicht aus
einer CSV). Weicht der live abgerufene Zustand vom erwarteten Ausgangszustand
ab (z.B. website ist nicht mehr leer, status ist nicht mehr "prospect"), wird
der Schritt uebersprungen und im Bericht explizit gemeldet, statt zu
ueberschreiben. Fuer Punkt 3 (Neuanlagen) gilt die bereits bestehende
Duplikat-Check-Logik aus scripts/import_kanzlei_domains_20260713.py
(CompanyMatcher: exakter Website-Domain-Match, dann Fuzzy-Namensvergleich
ueber services/name_matching.py).

Die 37 neuen Kanzleien/Kontakte (Punkt 3+4) werden NICHT im Skript
hartkodiert, sondern aus der Originaldatei
import_neue_kanzleien_final_v2_20260730.csv gelesen, die 1:1 (Byte-fuer-Byte,
keine manuelle Abschrift) in den S3-Bucket unter _diagnostics/ hochgeladen
wurde - vermeidet Transkriptionsfehler bei den Kontaktdaten.

Dry-Run per Default (zeigt nur, was passieren wuerde) - --apply fuer den
echten Lauf.

Usage (aus backend/, mit aktiviertem venv, in der Produktions-Console):

    python scripts/sync_lukas_kanzlei_export_20260730.py
    python scripts/sync_lukas_kanzlei_export_20260730.py --apply
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.core.config import get_settings  # noqa: E402
from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.enums import ClientStatus  # noqa: E402
from cc_crm.repositories.contacts import ContactPersonRepository  # noqa: E402
from cc_crm.schemas.client_company import ClientCompanyCreate  # noqa: E402
from cc_crm.services.clients import ClientCompanyService  # noqa: E402
from cc_crm.services.name_matching import (  # noqa: E402
    SIMILARITY_THRESHOLD,
    name_similarity,
    normalize_company_name,
)
from cc_crm.services.storage import _s3_client, _s3_configured  # noqa: E402

NEW_COMPANIES_S3_KEY = "_diagnostics/import_neue_kanzleien_final_v2_20260730.csv"
NEW_COMPANIES_LOCAL_FALLBACK = Path("/tmp/import_neue_kanzleien_final_v2_20260730.csv")

# ---------------------------------------------------------------------------
# Punkt 1: Website-Korrekturen an 4 bestehenden Kanzleien - nur setzen, wenn
# das Feld beim LIVE-Abruf tatsaechlich noch leer ist.
# ---------------------------------------------------------------------------
WEBSITE_CORRECTIONS = [
    {
        "id": "baef0f5f-98e2-4ebb-8387-5f021ea3ca8c",
        "name": "Plininger & Partner",
        "website": "https://plininger.org",
    },
    {
        "id": "d669e7fc-8945-4f2e-88b2-e4c4dc7e691a",
        "name": "Rass & Osinski Steuerberater Partnerschaftsgesellschaft mbB",
        "website": "https://steuerkanzlei-im-lehel.de",
    },
    {
        "id": "340de540-69d6-430c-9aab-4cf1a6d5a6ec",
        "name": "Götz & Partner mbB",
        "website": "https://goetz-partner.de",
    },
    {
        "id": "33e1f888-d7b6-4ba5-b689-deee173c16ff",
        "name": "Dipl.-Kfm. Sven Hase Wirtschaftsprüfer Steuerberater",
        "website": "https://svenhase.de",
    },
]

FORVISMAZARS_NOTE = {
    "id": "df14d67b-1433-4f35-9872-d06eaaa79d12",
    "name": "Forvismazars",
    "note_addition": "Frühere Korrespondenz-Domain vor Fusion: mazars.de",
}

# ---------------------------------------------------------------------------
# Punkt 2: 7 bestehende Kanzleien auf BLOCKED setzen - nur wenn der Status
# beim LIVE-Abruf noch "prospect" ist (siehe bestehende_kanzleien_blocked_
# 20260730.csv, hier 1:1 uebernommen).
# ---------------------------------------------------------------------------
BLOCK_CORRECTIONS = [
    {"id": "d0b276ce-9856-416e-ba3d-5ea1c16bb14e", "name": "Arbeit Anwalt"},
    {"id": "4981cc34-f0f7-49bd-8275-8d6a34109ff8", "name": "Wlw Partner"},
    {"id": "949e0b84-cf38-4e14-8971-224fd7a68ee3", "name": "Steuerberater Weilamrhein"},
    {"id": "458de5b0-3498-423a-b984-54c0f214158d", "name": "Attachenet"},
    {"id": "751a79b3-3404-45c4-a0bc-b0b51ca81675", "name": "Muth Partner"},
    {"id": "9b13a9c8-6868-4284-9cba-1cd36c9b5ce1", "name": "Con Tax"},
    {"id": "2345ad89-5dd3-49f0-9767-9cd188f78a73", "name": "Heuking"},
]

# Punkt 4: Sonder-Notiz fuer elbkanzlei.com (Streit-/Beschwerdekontakt).
SPECIAL_COMPANY_NOTES = {
    "elbkanzlei.com": (
        "Streit-/Beschwerde-Kontakt, kein Recruiting-Bezug, "
        "als Do-Not-Contact hinterlegt."
    ),
}

NEW_COMPANIES_HEADER = [
    "domain",
    "firmenname",
    "kontakt_vorname",
    "kontakt_nachname",
    "kontakt_titel",
    "kontakt_email",
    "kontakt_telefon",
    "telefon_typ",
    "is_primary",
    "status",
]


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _derive_name_from_domain(domain: str) -> str:
    """Nutzer-Vorgabe: falls firmenname leer ist, den Namen aus der Domain
    ableiten (nur fuers CRM-Feld, nicht in die Quelldatei zurueckschreiben)."""
    stem = domain.split(".", 1)[0]
    words = stem.replace("-", " ").replace("_", " ").split()
    return " ".join(word.capitalize() for word in words) or domain


def load_new_companies_csv() -> str:
    """Laedt die 1:1 hochgeladene Originaldatei aus S3 (oder, falls S3 nicht
    erreichbar ist, aus einem lokalen Fallback-Pfad) - bewusst NICHT
    hartkodiert im Skript, um Transkriptionsfehler bei 37 Kontaktdatensaetzen
    zu vermeiden."""
    if _s3_configured():
        settings = get_settings()
        response = _s3_client().get_object(Bucket=settings.s3_bucket, Key=NEW_COMPANIES_S3_KEY)
        return response["Body"].read().decode("utf-8-sig")
    if NEW_COMPANIES_LOCAL_FALLBACK.exists():
        return NEW_COMPANIES_LOCAL_FALLBACK.read_text(encoding="utf-8-sig")
    raise RuntimeError(
        f"Weder S3 konfiguriert noch lokaler Fallback vorhanden "
        f"({NEW_COMPANIES_LOCAL_FALLBACK}) - Quelldatei fuer Punkt 3 fehlt."
    )


def parse_new_companies_csv(text: str) -> list[dict[str, str]]:
    """Manuelles Semikolon-Split statt csv.reader: die "hinweis"-Spalte (nicht
    Teil von NEW_COMPANIES_HEADER, nur informativ) enthaelt selbst
    unmaskierte Semikolons (Freitext mit Adressen/Zusatzinfos) - ein
    generischer CSV-Parser wuerde die Zeile dadurch in zu viele Felder
    aufspalten. Da "hinweis" fuer keine Anlegen-/Aktualisieren-Entscheidung
    dieses Skripts gebraucht wird (alle Sonderfaelle sind bereits explizit in
    SPECIAL_COMPANY_NOTES/dem Status der jeweiligen Zeile abgebildet), wird
    hier bewusst robust nur auf die ersten 10 Spalten geparst."""
    lines = [line for line in text.strip("\r\n").split("\n") if line.strip()]
    header = [part.strip() for part in lines[0].split(";")[:10]]
    if header != NEW_COMPANIES_HEADER:
        raise RuntimeError(f"Unerwarteter CSV-Header: {header}")
    rows = []
    for line in lines[1:]:
        parts = line.split(";")
        row = dict(zip(NEW_COMPANIES_HEADER, (p.strip() for p in parts[:10]), strict=True))
        row["hinweis"] = ";".join(parts[10:]).strip()
        rows.append(row)
    return rows


class CompanyMatcher:
    """1:1 aus scripts/import_kanzlei_domains_20260713.py uebernommen (siehe
    dort fuer die vollstaendige Begruendung) - dieselbe, bereits im CRM
    etablierte Duplikat-Check-Logik: exakter Website-Domain-Match, dann
    Fuzzy-Namensvergleich (services/name_matching.py, SIMILARITY_THRESHOLD)."""

    def __init__(self, session: Session) -> None:
        self.session = session
        existing = session.query(ClientCompany).all()
        self._normalized_names: list[tuple[ClientCompany, str]] = [
            (client, normalize_company_name(client.name)) for client in existing
        ]
        self._by_website_domain: dict[str, ClientCompany] = {}
        for client in existing:
            if client.website:
                self._by_website_domain[_normalize_domain(client.website)] = client

    @property
    def preloaded_count(self) -> int:
        return len(self._normalized_names)

    def find_by_website(self, domain: str) -> ClientCompany | None:
        return self._by_website_domain.get(domain)

    def find_by_fuzzy_name(self, name: str) -> tuple[ClientCompany, float] | None:
        if not name:
            return None
        target = normalize_company_name(name)
        best: tuple[ClientCompany, float] | None = None
        for client, normalized in self._normalized_names:
            score = name_similarity(target, normalized)
            if score < SIMILARITY_THRESHOLD:
                continue
            if best is None or score > best[1]:
                best = (client, score)
        return best

    def register(self, client: ClientCompany) -> None:
        self._normalized_names.append((client, normalize_company_name(client.name)))
        if client.website:
            self._by_website_domain[_normalize_domain(client.website)] = client


def _normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0]
    return value.removeprefix("www.")


def apply_website_corrections(session: Session, *, apply: bool) -> tuple[dict[str, int], list[str]]:
    stats = {"applied": 0, "skipped_not_empty": 0, "skipped_not_found": 0}
    details = []
    for item in WEBSITE_CORRECTIONS:
        company = session.get(ClientCompany, uuid.UUID(item["id"]))
        if company is None:
            stats["skipped_not_found"] += 1
            details.append(f"NICHT GEFUNDEN (ID {item['id']}): {item['name']}")
            continue
        if company.website:
            stats["skipped_not_empty"] += 1
            details.append(
                f"UEBERSPRUNGEN ({company.name}): website live bereits gesetzt "
                f"({company.website!r}), nicht ueberschrieben"
            )
            continue
        action = "GESETZT" if apply else "WUERDE SETZEN"
        details.append(f"{action}: {company.name} -> website={item['website']}")
        if apply:
            company.website = item["website"]
        stats["applied"] += 1
    return stats, details


def apply_forvismazars_note(session: Session, *, apply: bool) -> str:
    company = session.get(ClientCompany, uuid.UUID(FORVISMAZARS_NOTE["id"]))
    if company is None:
        return f"NICHT GEFUNDEN (ID {FORVISMAZARS_NOTE['id']}): Forvismazars"
    addition = FORVISMAZARS_NOTE["note_addition"]
    if company.notes and addition in company.notes:
        return "UEBERSPRUNGEN: Forvismazars-Notiz bereits vorhanden"
    action = "ERGAENZT" if apply else "WUERDE ERGAENZEN"
    if apply:
        company.notes = f"{company.notes}\n{addition}" if company.notes else addition
    return f"{action}: Forvismazars-Notiz ({addition!r})"


def apply_block_corrections(session: Session, *, apply: bool) -> tuple[dict[str, int], list[str]]:
    stats = {"applied": 0, "skipped_not_prospect": 0, "skipped_not_found": 0}
    details = []
    for item in BLOCK_CORRECTIONS:
        company = session.get(ClientCompany, uuid.UUID(item["id"]))
        if company is None:
            stats["skipped_not_found"] += 1
            details.append(f"NICHT GEFUNDEN (ID {item['id']}): {item['name']}")
            continue
        if company.status != ClientStatus.PROSPECT:
            stats["skipped_not_prospect"] += 1
            details.append(
                f"UEBERSPRUNGEN ({company.name}): Status live bereits "
                f"{company.status!r}, nicht ueberschrieben"
            )
            continue
        action = "GESETZT" if apply else "WUERDE SETZEN"
        details.append(f"{action}: {company.name} -> status=blocked")
        if apply:
            company.status = ClientStatus.BLOCKED
        stats["applied"] += 1
    return stats, details


def apply_new_companies(
    session: Session, matcher: CompanyMatcher, rows: list[dict[str, str]], *, apply: bool
) -> tuple[dict[str, int], list[str]]:
    client_service = ClientCompanyService(session)
    contact_repo = ContactPersonRepository(session)
    stats = {
        "companies_created": 0,
        "companies_duplicate": 0,
        "contacts_created": 0,
        "contacts_with_phone": 0,
        "contacts_primary": 0,
    }
    details: list[str] = []

    # Gruppieren nach Domain, Zeilenreihenfolge erhalten (fuer den Fall
    # mehrerer Kontakte derselben Kanzlei, siehe Modul-Docstring/Bansbach).
    domains_in_order: list[str] = []
    rows_by_domain: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        domain = _normalize_domain(row["domain"])
        if domain not in rows_by_domain:
            domains_in_order.append(domain)
            rows_by_domain[domain] = []
        rows_by_domain[domain].append(row)

    for domain in domains_in_order:
        domain_rows = rows_by_domain[domain]
        first_row = domain_rows[0]
        firmenname = _clean(first_row["firmenname"])
        name = firmenname or _derive_name_from_domain(domain)
        status_value = _clean(first_row["status"]).lower()
        status = ClientStatus.BLOCKED if status_value == "blocked" else ClientStatus.PROSPECT

        existing = matcher.find_by_website(domain)
        duplicate_reason = None
        # Fuzzy-Namensvergleich NUR, wenn firmenname wirklich aus der Quelle
        # stammt - bei einem aus der Domain abgeleiteten Platzhalternamen
        # (z.B. "Elbkanzlei") ist ein Aehnlichkeits-Treffer kein verlaessliches
        # Duplikat-Signal und wuerde z.B. elbkanzlei.com (Punkt 4: MUSS neu
        # angelegt werden) faelschlich als Duplikat einer unverwandten
        # Kanzlei uebersehen lassen.
        if existing is None and firmenname:
            fuzzy = matcher.find_by_fuzzy_name(name)
            if fuzzy is not None:
                existing, score = fuzzy
                duplicate_reason = (
                    f"Namens-Aehnlichkeit {score:.2f} zu bestehender Kanzlei {existing.name!r}"
                )

        if existing is not None:
            stats["companies_duplicate"] += 1
            reason = duplicate_reason or "Website-Domain-Match"
            details.append(
                f"KANZLEI UEBERSPRUNGEN (Duplikat, {reason}): {name} ({domain}) "
                f"-> bestehende ID {existing.id}"
            )
            company = existing
        else:
            action = "ANGELEGT" if apply else "WUERDE ANLEGEN"
            note = SPECIAL_COMPANY_NOTES.get(domain)
            details.append(
                f"KANZLEI {action}: {name} (https://{domain}, status={status.value})"
                + (f" + Notiz: {note!r}" if note else "")
            )
            if apply:
                company = client_service.create(
                    ClientCompanyCreate(
                        name=name,
                        website=f"https://{domain}",
                        status=status,
                        notes=note,
                    )
                )
                matcher.register(company)
            else:
                company = None  # type: ignore[assignment]  # nur fuer Dry-Run-Anzeige der Kontakte unten
            stats["companies_created"] += 1

        for row in domain_rows:
            first_name = _clean(row["kontakt_vorname"])
            last_name = _clean(row["kontakt_nachname"])
            email = _clean(row["kontakt_email"])
            if not first_name and not last_name:
                # Wie im bestehenden Kanzlei-Kontakte-Import (siehe
                # import_kanzlei_domains_20260713.py): Fallback auf den
                # E-Mail-Lokalteil statt last_name leer zu lassen (DB-Spalte
                # ist NOT NULL) - kein erfundener Name, nur der bereits in
                # der Quelle vorhandene Lokalteil.
                last_name = email.split("@", 1)[0] if email else "(unbekannt)"
            phone = _clean(row["kontakt_telefon"]) or None
            is_primary = _clean(row["is_primary"]).lower() == "true"
            role_title = _clean(row["kontakt_titel"]) or None

            action = "ANGELEGT" if apply else "WUERDE ANLEGEN"
            details.append(
                f"  KONTAKT {action}: {first_name} {last_name} <{email or 'keine E-Mail'}>"
                f"{' (Tel: ' + phone + ')' if phone else ' (kein Telefon)'}"
                f"{' [HAUPTKONTAKT]' if is_primary else ''}"
            )
            if apply:
                contact_repo.create(
                    {
                        "client_company_id": company.id,
                        "first_name": first_name,
                        "last_name": last_name,
                        "email": email or None,
                        "phone": phone,
                        "role_title": role_title,
                        "is_primary": is_primary,
                    }
                )
            stats["contacts_created"] += 1
            if phone:
                stats["contacts_with_phone"] += 1
            if is_primary:
                stats["contacts_primary"] += 1

    return stats, details


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Tatsächlich schreiben (Default: Dry-Run)"
    )
    args = parser.parse_args()
    apply = args.apply

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== Lukas-Kanzlei-Sync ({mode}) ===\n")

    new_companies_text = load_new_companies_csv()
    new_rows = parse_new_companies_csv(new_companies_text)
    print(f"Neue-Kanzleien-CSV geladen: {len(new_rows)} Zeilen")

    session = SessionLocal()
    try:
        print("\n--- Punkt 1: Website-Korrekturen ---")
        website_stats, website_details = apply_website_corrections(session, apply=apply)
        for line in website_details:
            print(f"  {line}")
        forvismazars_result = apply_forvismazars_note(session, apply=apply)
        print(f"  {forvismazars_result}")

        print("\n--- Punkt 2: Bestandskanzleien auf BLOCKED ---")
        block_stats, block_details = apply_block_corrections(session, apply=apply)
        for line in block_details:
            print(f"  {line}")

        print("\n--- Punkt 3+4: Neue Kanzleien + Kontakte ---")
        matcher = CompanyMatcher(session)
        print(f"  Bestehende Kanzleien fuer Duplikat-Check geladen: {matcher.preloaded_count}")
        new_stats, new_details = apply_new_companies(session, matcher, new_rows, apply=apply)
        for line in new_details:
            print(f"  {line}")

        if apply:
            session.commit()
        else:
            session.rollback()
    finally:
        session.close()

    print("\n=== Zusammenfassung ===")
    print(
        f"Website-Korrekturen angewendet: {website_stats['applied']}/4 "
        f"(uebersprungen nicht-leer: {website_stats['skipped_not_empty']}, "
        f"nicht gefunden: {website_stats['skipped_not_found']})"
    )
    print(
        f"Bestandskanzleien auf BLOCKED gesetzt: {block_stats['applied']}/7 "
        f"(uebersprungen nicht-prospect: {block_stats['skipped_not_prospect']}, "
        f"nicht gefunden: {block_stats['skipped_not_found']})"
    )
    print(
        f"Neue Kanzleien angelegt: {new_stats['companies_created']} "
        f"(als Duplikat erkannt und uebersprungen: {new_stats['companies_duplicate']})"
    )
    print(
        f"Kontakte angelegt: {new_stats['contacts_created']} "
        f"(mit Telefonnummer: {new_stats['contacts_with_phone']}, "
        f"als Hauptkontakt markiert: {new_stats['contacts_primary']})"
    )
    if not apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
