"""Ergaenzt fehlende Ansprechpartner (ContactPerson) fuer Kanzleien
(ClientCompany), die bereits als Domain-Match aus dem vollstaendigen
Lukas-Postfach-Abgleich bekannt sind, aber noch KEINEN einzigen Kontakt
hinterlegt haben - rein additiv, siehe "KRITISCHE EINSCHRAENKUNG" unten.

Herkunft der Daten: kanzlei_kontakt_kandidaten_lukas_postfach.py (neben
diesem Skript) - ein aus dem vollstaendigen Postfach-Export
(lukas_pst_export.csv, 6128 Mails) abgeleitetes Python-Modul (analog
kanzlei_import_data.py), weil backend/scripts/*.csv projektweit gitignored
ist und diese Daten damit garantiert mit dem Repository deployed werden
(Lauf ueber die DO-App-Platform-Console, kein lokaler Dateizugriff dort).
Enthaelt bewusst NUR die bereits abgeleiteten, priorisierten Kandidaten
(1-3 Personen/Postfaecher je Domain) - NICHT den vollstaendigen
Rohdaten-Export (Datensparsamkeit, siehe dessen Modul-Docstring).

WICHTIG - warum hier NICHT domains_im_crm_aber_kein_kontakt.csv gelesen
wird: die im Auftrag genannte Datei (305 Domains ohne Kontakt) existierte
zum Zeitpunkt der Skripterstellung nicht im
"C:\\Users\\comma\\Claude\\Projects\\Commandeur Consulting GmbH\\"-Ordner.
Statt sich auf eine moeglicherweise veraltete/fehlende Vorabliste zu
verlassen, ermittelt dieses Skript "hat aktuell keinen Kontakt" IMMER live
per DB-Abfrage zum Ausfuehrungszeitpunkt - das erfuellt die im Auftrag
selbst explizit geforderte Live-Pruefung (Kanzleien koennten zwischenzeitlich
durch import_kanzleien_aus_lukas_postfach.py oder manuell ergaenzt worden
sein) sogar strikter, als es das Lesen einer statischen CSV koennte.

KRITISCHE EINSCHRAENKUNG (Nutzer-Vorgabe, unbedingt eingehalten):
- Es werden NIE ClientCompany-Datensaetze zusammengefuehrt, geloescht, neu
  angelegt oder deren id geaendert - dieses Skript liest ClientCompany nur
  lesend (Domain-Match) und setzt hoechstens das leere email-Feld.
- Es werden NIE bestehende ContactPerson-Datensaetze veraendert oder
  geloescht - ausschliesslich contact_repo.create() fuer neue Zeilen.
- Bestehende, nicht-leere ClientCompany-Felder (name, status, kanzleigruppe,
  fee_percentage, honorar_stufe, alle Commercial-Felder) werden nie
  angefasst. Von den im Auftrag genannten Adressfeldern liefert dieses
  Skript nur email (aus der Kontakt-E-Mail, nur wenn ClientCompany.email
  aktuell leer ist) - fuer street/postal_code/city/region/website liegen aus
  dem Postfach keine Daten vor, die dieses Skript befuellen koennte.
- Domain-Matching ausschliesslich exakt ueber ClientCompany.website/email-
  Domain (normalize_domain(), identisch zu
  import_kanzleien_aus_lukas_postfach.py) - KEIN Fuzzy-Namensvergleich
  (siehe Projektnotiz zu False-Positives bei Namensaehnlichkeit,
  project_fuzzy_dedup_placeholder_name_risk).
- "Hat aktuell keinen Kontakt" UND der Duplikat-Check (Kontakt mit
  gleicher E-Mail unter dieser Kanzlei existiert bereits) laufen live gegen
  die aktuelle DB zum Ausfuehrungszeitpunkt, nicht gegen eine gecachte Liste.

Ablauf pro Domain aus DOMAIN_CONTACT_CANDIDATES:
1. Domain -> passende(n) ClientCompany(s) live per website/email-Domain
   aufloesen (kein Treffer -> uebersprungen, "keine Domain-Uebereinstimmung
   mehr in der DB gefunden").
2. Pro gefundener Kanzlei: hat sie JETZT (live) schon mindestens einen
   Kontakt? Wenn ja -> komplett uebersprungen (kein Kontakt wird ergaenzt,
   auch wenn nur 1 von 3 Kandidaten-Kontakten schon existiert - das Ziel
   ist ausschliesslich, Kanzleien mit NULL Kontakten zu befuellen).
3. Sonst: fuer jeden der bis zu 3 Kandidaten (E-Mail-Duplikat unter dieser
   Kanzlei -> uebersprungen) einen neuen ContactPerson anlegen
   (role_title=None, is_primary=False). first_name/last_name kommen bereits
   vorgeteilt aus dem Datenmodul (leer, wenn im Postfach kein Name
   ermittelbar war - kein Raten, siehe dessen Docstring).
4. War ClientCompany.email vorher leer, wird es mit der E-Mail des ersten
   angelegten Kontakts befuellt (sonst unveraendert).

Usage (aus backend/, mit aktiviertem venv, ueber die DO-App-Platform-Console
des Backend-Containers):

    python scripts/enrich_kanzlei_kontakte_aus_lukas_postfach.py
    python scripts/enrich_kanzlei_kontakte_aus_lukas_postfach.py --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kanzlei_kontakt_kandidaten_lukas_postfach import (  # noqa: E402
    DOMAIN_CONTACT_CANDIDATES,
)
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.contact_person import ContactPerson  # noqa: E402
from cc_crm.repositories.contacts import ContactPersonRepository  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "enrich_kanzlei_kontakte_review.csv"

CSV_FIELDS = [
    "domain",
    "client_company_id",
    "client_company_name",
    "candidate_email",
    "candidate_first_name",
    "candidate_last_name",
    "anzahl_mails",
    "typ",
    "aktion",
    "error",
]


def normalize_domain(value: str) -> str:
    """Identisch zu import_kanzleien_aus_lukas_postfach.py::normalize_domain -
    Entfernt Schema (http/https), 'www.' und trailing slash, lowercased."""
    value = (value or "").strip().lower()
    if "://" in value:
        value = urlparse(value).netloc or value
    value = value.removeprefix("www.")
    return value.rstrip("/")


def build_domain_index(session: Session) -> dict[str, list[ClientCompany]]:
    """Domain (normalisiert) -> Liste der ClientCompany-Datensaetze, die
    ueber website ODER email auf diese Domain aufloesen - live aus der
    aktuellen DB gelesen (KEIN Fuzzy-Namensvergleich, nur exakter
    Domain-Match, siehe Modul-Docstring)."""
    index: dict[str, list[ClientCompany]] = {}
    for client in session.query(ClientCompany).all():
        domains: set[str] = set()
        if client.website:
            domains.add(normalize_domain(client.website))
        if client.email and "@" in client.email:
            domains.add(normalize_domain(client.email.split("@", 1)[1]))
        for domain in domains:
            if not domain:
                continue
            bucket = index.setdefault(domain, [])
            if client not in bucket:
                bucket.append(client)
    return index


class CompanyContactState:
    """Lazy geladener, EINMAL zu Beginn der Verarbeitung EINER Kanzlei
    gezogener Live-Schnappschuss ihrer bestehenden Kontakt-E-Mails (lowercase)
    - danach lokal fortgeschrieben, wenn dieses Skript selbst neue Kontakte
    anlegt, damit ein zweiter Kandidat derselben Domain im selben Lauf keinen
    Duplikat-Versuch ausloest. Wird PRO KANZLEI genau einmal gebaut (kein
    wiederholtes Neu-Abfragen), das Attribut had_contact_before_run
    entscheidet ueber die gesamte 1-3-Kandidaten-Gruppe dieser Domain."""

    def __init__(self, session: Session, company: ClientCompany) -> None:
        existing = (
            session.query(ContactPerson)
            .filter(ContactPerson.client_company_id == company.id)
            .all()
        )
        self.existing_emails: set[str] = {
            contact.email.strip().lower() for contact in existing if contact.email
        }
        self.had_contact_before_run = len(existing) > 0


def enrich(*, apply: bool) -> tuple[dict[str, int], list[dict[str, object]]]:
    with SessionLocal() as session:
        domain_index = build_domain_index(session)
        contact_repo = ContactPersonRepository(session)
        company_states: dict[uuid.UUID, CompanyContactState] = {}

        stats = {
            "domains_checked": len(DOMAIN_CONTACT_CANDIDATES),
            # Domain-Ebene: Anzahl Domains mit mindestens einem ClientCompany-
            # Treffer (companies nicht leer) - separat von den folgenden drei
            # Kontakt-/Kanzlei-Ebene-Zaehlern gefuehrt, weil eine einzelne
            # Domain ueber mehrere passende ClientCompany-Datensaetze
            # (Duplikate/Altlasten) UND ueber bis zu 3 neue Kontakte pro
            # Kanzlei mehr als einen Beitrag zu created/skipped_existing_
            # contact liefern kann. domains_checked - skipped_no_domain_match
            # == domains_with_match; created + skipped_existing_contact kann
            # deshalb GROESSER als domains_with_match sein - das ist erwartet,
            # keine Dopplung (siehe Nutzer-Nachfrage 2026-09-10: 292+287+496
            # = 1075 != 1061 Domains, aufgeklaert auf genau diese Weise).
            "domains_with_match": 0,
            "created": 0,
            "skipped_existing_contact": 0,
            "skipped_no_domain_match": 0,
            "errors": 0,
        }
        review_rows: list[dict[str, object]] = []

        for domain in sorted(DOMAIN_CONTACT_CANDIDATES):
            candidates = DOMAIN_CONTACT_CANDIDATES[domain]
            companies = domain_index.get(domain, [])

            if not companies:
                stats["skipped_no_domain_match"] += 1
                review_rows.append(
                    {
                        "domain": domain,
                        "client_company_id": "",
                        "client_company_name": "",
                        "candidate_email": "",
                        "candidate_first_name": "",
                        "candidate_last_name": "",
                        "anzahl_mails": "",
                        "typ": "",
                        "aktion": "UEBERSPRUNGEN (keine Domain-Uebereinstimmung mehr in der DB)",
                        "error": "",
                    }
                )
                continue

            stats["domains_with_match"] += 1
            for company in companies:
                if company.id not in company_states:
                    company_states[company.id] = CompanyContactState(session, company)
                state = company_states[company.id]

                if state.had_contact_before_run:
                    stats["skipped_existing_contact"] += 1
                    review_rows.append(
                        {
                            "domain": domain,
                            "client_company_id": str(company.id),
                            "client_company_name": company.name,
                            "candidate_email": "",
                            "candidate_first_name": "",
                            "candidate_last_name": "",
                            "anzahl_mails": "",
                            "typ": "",
                            "aktion": "UEBERSPRUNGEN (Kanzlei hat bereits einen Kontakt)",
                            "error": "",
                        }
                    )
                    continue

                for candidate in candidates:
                    email = candidate["email"].strip().lower()
                    review_row: dict[str, object] = {
                        "domain": domain,
                        "client_company_id": str(company.id),
                        "client_company_name": company.name,
                        "candidate_email": email,
                        "candidate_first_name": candidate["first_name"],
                        "candidate_last_name": candidate["last_name"],
                        "anzahl_mails": candidate["anzahl_mails"],
                        "typ": candidate["typ"],
                        "aktion": "",
                        "error": "",
                    }

                    if email in state.existing_emails:
                        stats["skipped_existing_contact"] += 1
                        review_row["aktion"] = (
                            "UEBERSPRUNGEN (Kontakt mit dieser E-Mail existiert bereits)"
                        )
                        review_rows.append(review_row)
                        continue

                    if apply:
                        try:
                            contact_repo.create(
                                {
                                    "client_company_id": company.id,
                                    "first_name": candidate["first_name"],
                                    "last_name": candidate["last_name"],
                                    "email": email,
                                    "phone": None,
                                    "role_title": None,
                                    "is_primary": False,
                                }
                            )
                            if not company.email:
                                company.email = email
                            session.commit()
                            stats["created"] += 1
                            state.existing_emails.add(email)
                            review_row["aktion"] = "ANGELEGT"
                        except Exception as exception:  # noqa: BLE001 - eine Zeile darf den Lauf nicht abbrechen
                            session.rollback()
                            stats["errors"] += 1
                            review_row["aktion"] = "FEHLER"
                            review_row["error"] = str(exception)[:300]
                    else:
                        stats["created"] += 1
                        state.existing_emails.add(email)
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

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Kanzlei-Kontakte aus Lukas-Postfach ergaenzen ({mode}) ===")
    print(f"Domains mit Kontakt-Kandidaten aus dem Postfach: {len(DOMAIN_CONTACT_CANDIDATES)}\n")

    stats, review_rows = enrich(apply=args.apply)
    _write_review_csv(review_rows)

    verb = "angelegt" if args.apply else "würden angelegt"
    print("\n=== Zusammenfassung (Domain-Ebene) ===")
    print(f"Geprüfte Domains (aus dem Postfach-Abgleich): {stats['domains_checked']}")
    print(f"  davon mit Domain-Treffer in der aktuellen DB: {stats['domains_with_match']}")
    print(
        "  davon ohne Domain-Übereinstimmung mehr in der DB: "
        f"{stats['skipped_no_domain_match']}"
    )
    print("\n=== Zusammenfassung (Kontakt-/Kanzlei-Ebene) ===")
    print(
        "Hinweis: eine einzelne Domain kann hier mehr als 1 beitragen - entweder weil "
        "mehrere ClientCompany-Datensätze dieselbe Domain nutzen (Duplikate/Altlasten), "
        "oder weil für eine Kanzlei bis zu 3 Kontakte auf einmal angelegt werden. Die "
        "folgenden Zahlen summieren sich deshalb NICHT auf 'Domains mit Domain-Treffer'."
    )
    print(f"Neue Kontakte {verb}: {stats['created']}")
    print(f"Übersprungen (Kontakt existiert bereits): {stats['skipped_existing_contact']}")
    print(f"Fehler: {stats['errors']}")
    print(f"\nReview-CSV: {OUTPUT_PATH}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Review-CSV prüfen, dann mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
