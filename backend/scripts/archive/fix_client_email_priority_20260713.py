"""Korrektur Phase N: behebt eine falsche Priorisierung im urspruenglichen
Kanzlei-Domain-Import (import_kanzlei_domains_20260713.py) - dort wurde
info@ bevorzugt, sobald mehrere Funktionspostfaecher fuer eine Domain
existierten. info@ landet aber haeufig in einem unzustaendigen
Sammel-Postfach; eine bewerbungs-/recruiting-bezogene Adresse oder eine
echte Person ist naeher am tatsaechlichen Ansprechpartner.

Korrigierte Prioritaet fuer ClientCompany.email (siehe
import_kanzlei_domains_20260713.py::pick_client_email(), hier wiederverwendet
statt dupliziert):
  1. bewerbung@ / karriere@ / recruiting@
  2. eine echte Personen-E-Mail-Adresse (Typ Person > Person (nur Nachname)
     > Unklar, bei Gleichstand alphabetisch nach Nachname)
  3. info@ (jetzt echter Notnagel)
  4. erstes verbleibendes Funktionspostfach in der Datei

Betrifft ALLE Domains mit Anzahl_Funktionspostfach > 0 (nicht nur die mit
mehreren Postfaechern - auch eine Domain mit genau einem Funktionspostfach
kann jetzt durch eine hoeher priorisierte Adresse ersetzt werden, siehe
Aufgabenstellung). Ueberschreibt den gespeicherten email-Wert nur, wenn er
vom neu berechneten Wert abweicht.

Ausfuehren:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\fix_client_email_priority_20260713.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from import_kanzlei_domains_20260713 import (  # noqa: E402
    CompanyMatcher,
    build_domain_mailboxes,
    build_domain_persons,
    load_contact_rows,
    load_domain_rows,
    normalize_domain,
    pick_client_email,
)

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402


def main() -> None:
    domain_rows = load_domain_rows()
    contact_rows = load_contact_rows()
    mailboxes = build_domain_mailboxes(contact_rows)
    persons = build_domain_persons(contact_rows)

    session = SessionLocal()
    try:
        matcher = CompanyMatcher(session)
        print(f"Bestehende Kanzleien geladen: {matcher.preloaded_count}")

        reason_counts: dict[str, int] = {}
        unchanged = 0
        no_company = 0
        examples: list[tuple[str, str, str, str]] = []  # (domain, alt, neu, grund)

        candidates = [row for row in domain_rows if int(row["Anzahl_Funktionspostfach"] or 0) > 0]
        print(f"Domains mit Funktionspostfach (zu pruefen): {len(candidates)}")

        for index, row in enumerate(candidates, start=1):
            domain = normalize_domain(row["Domain"])
            company = matcher.find_by_website(domain)
            if company is None:
                fuzzy = matcher.find_by_fuzzy_name(row["Firma_vermutet"].strip())
                company = fuzzy[0] if fuzzy is not None else None
            if company is None:
                no_company += 1
                continue

            new_email, reason = pick_client_email(
                mailboxes.get(domain, []), persons.get(domain, [])
            )
            old_email = company.email

            if new_email and new_email != old_email:
                if len(examples) < 10:
                    examples.append((domain, old_email or "(leer)", new_email, reason))
                company.email = new_email
                session.flush()
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            else:
                unchanged += 1

            if index % 200 == 0:
                session.commit()
                print(f"  ... {index}/{len(candidates)} geprueft")

        session.commit()
    finally:
        session.close()

    print("\n=== Zusammenfassung ===")
    total_changed = sum(reason_counts.values())
    print(f"Geaenderte Kanzleien gesamt: {total_changed}")
    for reason in ("bewerbung", "karriere", "recruiting", "person", "info", "first_functional"):
        print(f"  davon Grund={reason}: {reason_counts.get(reason, 0)}")
    print(f"Unveraendert (neuer Wert = alter Wert, oder keine E-Mail ermittelbar): {unchanged}")
    print(f"Keine Kanzlei zur Domain gefunden: {no_company}")

    print("\nStichprobe (Domain, alt, neu, Grund):")
    for domain, old_email, new_email, reason in examples:
        print(f"  {domain:35} {old_email!r:35} -> {new_email!r:35} ({reason})")


if __name__ == "__main__":
    main()
