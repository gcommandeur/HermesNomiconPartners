"""Importiert Kanzleien (ClientCompany) und Kontakte (ContactPerson) aus
Kanzlei_Domains_Uebersicht_20260713.csv und
Kanzlei_Kontakte_zum_Import_20260713.csv (Postfach-Domain-Sichtung).

Aufgabe 1 - Kanzleien: pro Domain-Zeile zuerst nach bestehendem Match suchen
(exakter website-Domain-Treffer, dann Fuzzy-Namensvergleich über den
bestehenden ClientCompanyService/name_matching.py, SIMILARITY_THRESHOLD=0.72)
- bei Treffer bestehende Kanzlei verwenden (website nachtragen, falls leer),
sonst neu anlegen mit status=PROSPECT und Modell-Defaults fuer alle
Vertragsfelder (keine Vertragsbasis vorhanden). Fuzzy-Matching wird NICHT
haerter gemacht als der bestehende Service - im Zweifel wird neu angelegt
(Nutzer bereinigt Duplikate danach manuell, wie bisher).

Aufgabe 2 - Kontakte: fuer Typ in {Person, "Person (nur Nachname)", Unklar}
wird ein ContactPerson an die per Domain aufgeloeste Kanzlei gehaengt.
Funktionspostfach-Zeilen werden NICHT als Kontakt angelegt - sie fliessen
stattdessen (Aufgabe 1) als ClientCompany.email ein.

Wichtig zu first_name: der Pydantic-Schema-Layer (ContactPersonCreate)
verlangt min_length=1 fuer first_name/last_name - das wuerde die explizite
Vorgabe "first_name leer lassen, wenn CSV-Feld leer ist" verletzen. Dieses
Skript legt Kontakte deshalb bewusst ueber das Repository direkt an (Dict statt
Pydantic-Modell), das keine Validierung erzwingt - der DB-Spalte selbst
(String, nullable=False) ist ein leerer String "" erlaubt, nur NULL nicht.

Performance: bestehende Kanzleinamen werden EINMAL geladen und normalisiert
(normalize_company_name), nicht pro Zeile neu aus der DB gelesen - sonst waere
der Fuzzy-Vergleich quadratisch langsam (1.146 Zeilen x N bestehende Kanzleien
pro Zeile).

Idempotent: mehrfache Ausfuehrung legt keine Duplikate an (Website-/Fuzzy-Match
fuer Kanzleien, exakter E-Mail-Match global fuer Kontakte - wie
import_outlook_contacts.py es bereits vormacht).

Prioritaet fuer ClientCompany.email (Korrektur Phase N, 2026-07-13 - urspruenglich
wurde info@ faelschlich bevorzugt, siehe pick_client_email()): 1) bewerbung@/
karriere@/recruiting@-Funktionspostfach, 2) eine echte Personen-Adresse (falls
fuer die Domain ein Person-/Person(nur Nachname)-/Unklar-Kontakt existiert),
3) info@ (jetzt echter Notnagel), 4) erstes verbleibendes Funktionspostfach.
Siehe scripts/fix_client_email_priority_20260713.py fuer den Korrekturlauf, der
diese Prioritaet nachtraeglich auf bereits importierte Kanzleien anwendet.

Ausfuehren:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\import_kanzlei_domains_20260713.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.contact_person import ContactPerson  # noqa: E402
from cc_crm.models.enums import ClientStatus  # noqa: E402
from cc_crm.repositories.contacts import ContactPersonRepository  # noqa: E402
from cc_crm.schemas.client_company import ClientCompanyCreate  # noqa: E402
from cc_crm.services.clients import ClientCompanyService  # noqa: E402
from cc_crm.services.name_matching import (  # noqa: E402
    SIMILARITY_THRESHOLD,
    name_similarity,
    normalize_company_name,
)

DOMAINS_CSV = Path(
    r"C:\Users\comma\Claude\Projects\Commandeur Consulting GmbH"
    r"\Kanzlei_Domains_Uebersicht_20260713.csv"
)
CONTACTS_CSV = Path(
    r"C:\Users\comma\Claude\Projects\Commandeur Consulting GmbH"
    r"\Kanzlei_Kontakte_zum_Import_20260713.csv"
)

CONTACT_TYPES_FOR_IMPORT = {"Person", "Person (nur Nachname)", "Unklar"}
FUNKTIONSPOSTFACH_TYPE = "Funktionspostfach"

# Rang fuer die Personen-Auswahl bei der E-Mail-Prioritaet (kleiner = bevorzugt):
# vollstaendiger Name vor "nur Nachname" vor "Unklar"; bei Gleichstand
# alphabetisch nach Nachname (siehe pick_client_email()).
PERSON_TYPE_RANK = {"Person": 0, "Person (nur Nachname)": 1, "Unklar": 2}

# Praefixe, die mechanisch per "startswith" statt exaktem Vergleich geprueft
# werden (faengt z.B. auch "bewerbungen@"/"karrieren@" als Variante von
# "bewerbung@"/"karriere@" ab) - reine Parsing-Robustheit, keine Dateninhalte-
# Entscheidung.
_PRIORITY_PREFIXES = ("bewerbung", "karriere", "recruiting")


def normalize_domain(value: str) -> str:
    """Entfernt Schema (http/https), 'www.' und trailing slash, lowercased -
    fuer den Domain-Vergleich zwischen Website-Feld und CSV-Domain. Die
    Kontakte-CSV enthaelt 20 Domains mit abweichender Gross-/Kleinschreibung
    gegenueber der Domains-CSV (z.B. "WestlakeVinnolit.com" vs.
    "westlakevinnolit.com") - deshalb wird ueberall lowercased verglichen."""
    value = value.strip().lower()
    if "://" in value:
        value = urlparse(value).netloc or value
    value = value.removeprefix("www.")
    return value.rstrip("/")


def _clean(value: str | None) -> str:
    return (value or "").strip()


def load_domain_rows() -> list[dict[str, str]]:
    with DOMAINS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_contact_rows() -> list[dict[str, str]]:
    with CONTACTS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_domain_mailboxes(contact_rows: list[dict[str, str]]) -> dict[str, list[str]]:
    """domain (normalisiert) -> Liste von Funktionspostfach-E-Mails, in
    Datei-Reihenfolge (fuer die "erstes verbleibendes Postfach"-Regel)."""
    mailboxes: dict[str, list[str]] = {}
    for row in contact_rows:
        if row["Typ"].strip() != FUNKTIONSPOSTFACH_TYPE:
            continue
        domain = normalize_domain(row["Domain"])
        email = _clean(row["Email"])
        if not email:
            continue
        mailboxes.setdefault(domain, []).append(email)
    return mailboxes


def build_domain_persons(contact_rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """domain (normalisiert) -> Liste der Person-/Person(nur Nachname)/Unklar-
    Zeilen (fuer die Personen-Prioritaetsstufe in pick_client_email())."""
    persons: dict[str, list[dict[str, str]]] = {}
    for row in contact_rows:
        if row["Typ"].strip() not in CONTACT_TYPES_FOR_IMPORT:
            continue
        if not _clean(row["Email"]):
            continue
        domain = normalize_domain(row["Domain"])
        persons.setdefault(domain, []).append(row)
    return persons


def pick_client_email(
    functional_emails: list[str], person_rows: list[dict[str, str]]
) -> tuple[str | None, str]:
    """Bestimmt die zu hinterlegende ClientCompany.email nach der Prioritaet
    aus Phase N (Korrektur): 1) bewerbung@/karriere@/recruiting@, 2) eine
    echte Personen-Adresse, 3) info@ (Notnagel), 4) erstes verbleibendes
    Funktionspostfach. Gibt (email, grund) zurueck, grund ist einer von
    "bewerbung"/"karriere"/"recruiting"/"person"/"info"/"first_functional"/
    "none" - fuer die Beleg-Aufschluesselung im Aufrufer."""
    for prefix in _PRIORITY_PREFIXES:
        for email in functional_emails:
            local_part = email.split("@", 1)[0].lower()
            if local_part.startswith(prefix):
                return email, prefix

    if person_rows:

        def sort_key(row: dict[str, str]) -> tuple[int, str]:
            rank = PERSON_TYPE_RANK.get(row["Typ"].strip(), 99)
            nachname = _clean(row.get("Nachname")).lower()
            return (rank, nachname)

        best_person = sorted(person_rows, key=sort_key)[0]
        return _clean(best_person["Email"]), "person"

    for email in functional_emails:
        if email.split("@", 1)[0].lower() == "info":
            return email, "info"

    if functional_emails:
        return functional_emails[0], "first_functional"

    return None, "none"


class CompanyMatcher:
    """Haelt einmalig geladene, normalisierte Kanzleinamen + Websites vor,
    damit der Fuzzy-Vergleich nicht pro CSV-Zeile die komplette DB-Tabelle neu
    normalisiert (quadratische Laufzeit vermeiden, siehe Modul-Docstring)."""

    def __init__(self, session: Session) -> None:
        self.session = session
        existing = session.query(ClientCompany).all()
        self._normalized_names: list[tuple[ClientCompany, str]] = [
            (client, normalize_company_name(client.name)) for client in existing
        ]
        self._by_website_domain: dict[str, ClientCompany] = {}
        for client in existing:
            if client.website:
                self._by_website_domain[normalize_domain(client.website)] = client

    @property
    def preloaded_count(self) -> int:
        return len(self._normalized_names)

    def find_by_website(self, domain: str) -> ClientCompany | None:
        return self._by_website_domain.get(domain)

    def find_by_fuzzy_name(self, name: str) -> tuple[ClientCompany, float] | None:
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
        """Traegt eine neu angelegte/aktualisierte Kanzlei in die In-Memory-
        Indizes ein, damit spaetere Zeilen im selben Lauf sie ebenfalls
        finden koennen (verhindert Dubletten innerhalb derselben CSV)."""
        self._normalized_names.append((client, normalize_company_name(client.name)))
        if client.website:
            self._by_website_domain[normalize_domain(client.website)] = client


def import_companies(
    session: Session,
    matcher: CompanyMatcher,
    domain_rows: list[dict[str, str]],
    mailboxes: dict[str, list[str]],
    persons: dict[str, list[dict[str, str]]],
) -> tuple[dict[str, ClientCompany], dict[str, int]]:
    client_service = ClientCompanyService(session)
    domain_to_company: dict[str, ClientCompany] = {}
    stats = {
        "created": 0,
        "reused_website": 0,
        "reused_fuzzy": 0,
        "email_filled": 0,
        "failed": 0,
    }

    for index, row in enumerate(domain_rows, start=1):
        domain = normalize_domain(row["Domain"])
        firma = _clean(row["Firma_vermutet"])
        anzahl_funktionspostfach = int(row["Anzahl_Funktionspostfach"] or 0)

        company = matcher.find_by_website(domain)
        if company is not None:
            stats["reused_website"] += 1
        else:
            fuzzy = matcher.find_by_fuzzy_name(firma)
            if fuzzy is not None:
                company = fuzzy[0]
                stats["reused_fuzzy"] += 1

        if company is None:
            try:
                company = client_service.create(
                    ClientCompanyCreate(
                        name=firma,
                        website=f"https://{domain}",
                        status=ClientStatus.PROSPECT,
                    )
                )
                stats["created"] += 1
                matcher.register(company)
            except Exception as exception:  # noqa: BLE001
                session.rollback()
                stats["failed"] += 1
                print(f"  FEHLER bei Domain {domain} ({firma}): {exception}")
                continue
        elif not company.website:
            company.website = f"https://{domain}"
            session.flush()
            matcher.register(company)

        if anzahl_funktionspostfach > 0 and not company.email:
            candidates = mailboxes.get(domain, [])
            email, _reason = pick_client_email(candidates, persons.get(domain, []))
            if email:
                company.email = email
                session.flush()
                stats["email_filled"] += 1

        domain_to_company[domain] = company

        if index % 200 == 0:
            session.commit()
            print(f"  ... {index}/{len(domain_rows)} Kanzlei-Zeilen verarbeitet")

    session.commit()
    return domain_to_company, stats


def import_contacts(
    session: Session,
    contact_rows: list[dict[str, str]],
    domain_to_company: dict[str, ClientCompany],
) -> dict[str, int]:
    contact_repo = ContactPersonRepository(session)
    stats = {"created": 0, "skipped_duplicate": 0, "skipped_no_company": 0, "failed": 0}

    for index, row in enumerate(contact_rows, start=1):
        typ = row["Typ"].strip()
        if typ not in CONTACT_TYPES_FOR_IMPORT:
            continue

        email = _clean(row["Email"])
        domain = normalize_domain(row["Domain"])
        company = domain_to_company.get(domain)
        if company is None:
            stats["skipped_no_company"] += 1
            continue

        if email and session.query(ContactPerson).filter_by(email=email).first() is not None:
            stats["skipped_duplicate"] += 1
            continue

        first_name = _clean(row["Vorname"])
        last_name = _clean(row["Nachname"]) or _clean(row["Rohe_Lokalteil"])

        try:
            contact_repo.create(
                {
                    "client_company_id": company.id,
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email or None,
                    "phone": None,
                    "role_title": None,
                    "is_primary": False,
                }
            )
            stats["created"] += 1
        except Exception as exception:  # noqa: BLE001
            session.rollback()
            stats["failed"] += 1
            print(f"  FEHLER bei Kontakt {email!r}: {exception}")
            continue

        if index % 300 == 0:
            session.commit()
            print(f"  ... {index}/{len(contact_rows)} Kontakt-Zeilen verarbeitet")

    session.commit()
    return stats


def main() -> None:
    domain_rows = load_domain_rows()
    contact_rows = load_contact_rows()
    print(f"Domain-Zeilen: {len(domain_rows)}")
    print(f"Kontakt-Zeilen: {len(contact_rows)}")

    mailboxes = build_domain_mailboxes(contact_rows)
    persons = build_domain_persons(contact_rows)

    session = SessionLocal()
    try:
        matcher = CompanyMatcher(session)
        print(f"Bestehende Kanzleien geladen: {matcher.preloaded_count}")

        print("\n--- Aufgabe 1: Kanzleien ---")
        domain_to_company, company_stats = import_companies(
            session, matcher, domain_rows, mailboxes, persons
        )

        print("\n--- Aufgabe 2: Kontakte ---")
        contact_stats = import_contacts(session, contact_rows, domain_to_company)
    finally:
        session.close()

    print("\n=== Zusammenfassung ===")
    print(f"Kanzleien neu angelegt (status=PROSPECT): {company_stats['created']}")
    print(f"Kanzleien wiederverwendet (Website-Match): {company_stats['reused_website']}")
    print(f"Kanzleien wiederverwendet (Fuzzy-Namens-Match): {company_stats['reused_fuzzy']}")
    print(f"Kanzleien mit Funktionspostfach-E-Mail befuellt: {company_stats['email_filled']}")
    print(f"Kanzlei-Anlage fehlgeschlagen: {company_stats['failed']}")
    print()
    print(f"Kontakte neu angelegt: {contact_stats['created']}")
    print(
        f"Kontakte uebersprungen (Duplikat, gleiche E-Mail): {contact_stats['skipped_duplicate']}"
    )
    print(f"Kontakte uebersprungen (keine Kanzlei gefunden): {contact_stats['skipped_no_company']}")
    print(f"Kontakt-Anlage fehlgeschlagen: {contact_stats['failed']}")


if __name__ == "__main__":
    main()
