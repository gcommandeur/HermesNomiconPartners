"""Import der 358 als 'kanzlei_bestaetigt' verifizierten Domains aus dem
vollstaendigen Lukas-Postfach-Abgleich (siehe
Kanzleien_Abgleich_Lukas_Postfach_vs_CRM_20260910.md) als neue ClientCompany-
Datensaetze (status=prospect).

Herkunft der Daten: von 443 Domains, die im vollstaendigen Postfach-Export
(6128 Mails) vorkommen, aber im CRM komplett fehlten, wurden in einer
zweistufigen Pruefung (Stufe 1: Pattern-Autoklassifikation ohne Web-Fetch;
Stufe 2: Web-Verifikation der uneindeutigen Domains per web_fetch) 358 als
echte Steuerberater-/Wirtschaftspruefungs-/Rechtsanwalts-/Treuhand-Kanzlei
(oder vergleichbare Organisation) bestaetigt (klassifikation=kanzlei_bestaetigt
in kanzleien_aus_lukas_postfach_input.csv, liegt neben diesem Skript). Die
restlichen Domains (nicht_kanzlei / unklar) werden von diesem Skript NICHT
angelegt, sondern nur im Abschlussbericht gezaehlt - sie bleiben Aufgabe fuer
ein spaeteres manuelles/gezieltes Review.

Datenquelle: kanzlei_import_data.py (KANZLEI_ROWS, neben diesem Skript) - ein
Python-Modul statt CSV, weil backend/scripts/*.csv projektweit gitignored ist
(personenbezogene Review-/Backfill-Dateien) und die Domain-Liste damit
garantiert mit dem Repository deployed wird. Enthaelt nur die 384 Domains mit
klassifikation=kanzlei_bestaetigt; die vollstaendige Liste inkl. nicht_kanzlei/
unklar und Begruendung liegt in domains_fehlend_verifiziert.csv.

Sicherheit/Idempotenz: Anders als bei Update-Skripten (siehe
sync_lukas_kanzlei_export_20260730.py) legt dieses Skript nur NEUE Datensaetze
an, veraendert aber nie bestehende - das Risiko beschraenkt sich auf
ungewollte Duplikate. Deshalb gilt bewusst NUR ein Domain-Match als Dublette
(ClientCompany.website, normalisiert) - KEIN Fuzzy-Namensvergleich. Viele der
hier verwendeten Namen sind Platzhalter (aus dem Domainnamen abgeleitet, wenn
kein Firmenname aus der Webseite extrahiert werden konnte), und ein aus einem
Nachnamen-Fragment abgeleiteter Platzhalter kann per Fuzzy-Matching leicht
falsch-positiv auf eine unverwandte, aber namensaehnliche Kanzlei matchen
(bestaetigtes systematisches Problem, siehe Projektnotiz zu
project_fuzzy_dedup_placeholder_name_risk). Der Domain-Check erfolgt live beim
Schreiben gegen die aktuelle DB (nicht gegen eine gecachte Vorabliste), damit
das Skript auch bei einem zweiten Lauf oder falls die Domain zwischenzeitlich
anderweitig angelegt wurde, keine Duplikate erzeugt.

!!! ACHTUNG: --apply schreibt echt in die Datenbank. Bitte VORHER ein
Datenbank-Backup ueber die DO-Console ausgefuehrt haben. !!!

Usage (aus backend/, mit aktiviertem venv, ueber die DO-App-Platform-Console
des Backend-Containers - siehe Abschlussbericht):

    python scripts/import_kanzleien_aus_lukas_postfach.py
    python scripts/import_kanzleien_aus_lukas_postfach.py --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.enums import ClientStatus  # noqa: E402
from cc_crm.schemas.client_company import ClientCompanyCreate  # noqa: E402
from cc_crm.services.clients import ClientCompanyService  # noqa: E402

from kanzlei_import_data import KANZLEI_ROWS  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "import_kanzleien_aus_lukas_postfach_review.csv"

CSV_FIELDS = [
    "domain",
    "klassifikation",
    "hat_geantwortet",
    "anzahl_mails",
    "name_verwendet",
    "aktion",
    "error",
]


def normalize_domain(value: str) -> str:
    """Entfernt Schema (http/https), 'www.' und trailing slash, lowercased -
    gleiche Logik wie in den anderen Kanzlei-Import-Skripten dieses Ordners."""
    value = (value or "").strip().lower()
    if "://" in value:
        value = urlparse(value).netloc or value
    value = value.removeprefix("www.")
    return value.rstrip("/")


def derive_name_from_domain(domain: str) -> str:
    """Fallback-Firmenname, wenn kein vermuteter_firmenname aus der Webseite
    extrahiert werden konnte: Domain ohne TLD, Bindestriche zu Leerzeichen,
    titelcased. Rein kosmetisch - der Nutzer korrigiert Kanzleinamen ohnehin
    routinemaessig manuell nach dem Import (wie bei den Vorlaeufer-Skripten)."""
    base = domain.split(".")[0]
    base = base.replace("-", " ").replace("_", " ")
    return base.title() or domain


def load_kanzlei_rows() -> list[dict[str, str]]:
    # KANZLEI_ROWS enthaelt bereits ausschliesslich klassifikation=kanzlei_bestaetigt
    # (siehe kanzlei_import_data.py). Wir geben trotzdem row["klassifikation"] im
    # Review-Output mit aus, deshalb wird das Feld hier ergaenzt.
    return [{**row, "klassifikation": "kanzlei_bestaetigt"} for row in KANZLEI_ROWS]


class ExistingDomainIndex:
    """Haelt die aktuell in der DB vorhandenen ClientCompany-Websites/E-Mails
    einmalig vor (normalisierte Domain -> True), damit pro CSV-Zeile nicht die
    komplette Tabelle neu gelesen werden muss. Wird bei jeder Neuanlage sofort
    ergaenzt, damit auch Domains, die mehrfach in der CSV vorkommen, innerhalb
    desselben Laufs nicht doppelt angelegt werden."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._domains: set[str] = set()
        for client in session.query(ClientCompany).all():
            if client.website:
                self._domains.add(normalize_domain(client.website))
            if client.email and "@" in client.email:
                self._domains.add(client.email.split("@", 1)[1].strip().lower())

    def contains(self, domain: str) -> bool:
        return domain in self._domains

    def register(self, domain: str) -> None:
        self._domains.add(domain)


def import_kanzleien(
    *, apply: bool, rows: list[dict[str, str]]
) -> tuple[dict[str, int], list[dict[str, object]]]:
    with SessionLocal() as session:
        index = ExistingDomainIndex(session)
        client_service = ClientCompanyService(session)

        stats = {
            "checked": len(rows),
            "created": 0,
            "skipped_existing_domain": 0,
            "errors": 0,
        }
        review_rows: list[dict[str, object]] = []

        for row in rows:
            domain = normalize_domain(row["domain"])
            review_row: dict[str, object] = {
                "domain": domain,
                "klassifikation": row["klassifikation"],
                "hat_geantwortet": row.get("hat_geantwortet", ""),
                "anzahl_mails": row.get("anzahl_mails", ""),
                "name_verwendet": "",
                "aktion": "",
                "error": "",
            }

            if not domain:
                review_row["aktion"] = "UEBERSPRUNGEN (leere Domain)"
                review_rows.append(review_row)
                continue

            if index.contains(domain):
                stats["skipped_existing_domain"] += 1
                review_row["aktion"] = "UEBERSPRUNGEN (Domain existiert bereits in ClientCompany)"
                review_rows.append(review_row)
                continue

            name = (row.get("vermuteter_firmenname") or "").strip() or derive_name_from_domain(
                domain
            )
            review_row["name_verwendet"] = name

            if apply:
                try:
                    client_service.create(
                        ClientCompanyCreate(
                            name=name,
                            website=f"https://{domain}",
                            status=ClientStatus.PROSPECT,
                        )
                    )
                    session.commit()
                    stats["created"] += 1
                    index.register(domain)
                    review_row["aktion"] = "ANGELEGT"
                except Exception as exception:  # noqa: BLE001 - eine Zeile darf den Lauf nicht abbrechen
                    session.rollback()
                    stats["errors"] += 1
                    review_row["aktion"] = "FEHLER"
                    review_row["error"] = str(exception)[:300]
            else:
                stats["created"] += 1
                index.register(domain)
                review_row["aktion"] = "WUERDE ANLEGEN"

            review_rows.append(review_row)

        return stats, review_rows


def _write_review_csv(rows: list[dict[str, object]]) -> None:
    if OUTPUT_PATH.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = OUTPUT_PATH.with_name(f"{OUTPUT_PATH.stem}_backup_{timestamp}.csv")
        suffix = 2
        while backup_path.exists():
            backup_path = OUTPUT_PATH.with_name(
                f"{OUTPUT_PATH.stem}_backup_{timestamp}_{suffix}.csv"
            )
            suffix += 1
        OUTPUT_PATH.rename(backup_path)
        print(f"Vorhandene Review-CSV gesichert nach: {backup_path}")

    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Tatsächlich schreiben (Default: Dry-Run)"
    )
    args = parser.parse_args()

    if args.apply:
        print(
            "!!! ACHTUNG: --apply schreibt echt in die Datenbank. Bitte VORHER ein "
            "Datenbank-Backup ueber die DO-Console ausgefuehrt haben. !!!\n"
        )

    rows = load_kanzlei_rows()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Import Kanzleien aus Lukas-Postfach-Abgleich ({mode}) ===")
    print("Quelle: kanzlei_import_data.py (KANZLEI_ROWS)")
    print(f"Domains mit klassifikation=kanzlei_bestaetigt: {len(rows)}\n")

    stats, review_rows = import_kanzleien(apply=args.apply, rows=rows)
    _write_review_csv(review_rows)

    print("\n=== Zusammenfassung ===")
    print(f"Geprüft (klassifikation=kanzlei_bestaetigt): {stats['checked']}")
    verb = "angelegt" if args.apply else "würden angelegt"
    print(f"Neu {verb} (status=prospect): {stats['created']}")
    print(
        "Übersprungen (Domain existiert bereits als ClientCompany.website/email): "
        f"{stats['skipped_existing_domain']}"
    )
    print(f"Fehler: {stats['errors']}")
    print(f"\nReview-CSV: {OUTPUT_PATH}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Review-CSV prüfen, dann mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
