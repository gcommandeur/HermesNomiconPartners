"""Sonderfaelle PwC/ETL/Ecovis (User-Vorgabe 2026-07-14, woertlich: "fuehre PWC
als einzelfall (nur einmal PWC Deutschland), ETL alle eigenstaendig behandeln
als waeren es andere kanzleien. ECOVIS wird eingeteilt in ECOVIS, ECOVIS KSO
und RTS ECOVIS").

Diese drei Marken werden bewusst ANDERS behandelt als es das allgemeine
Fuzzy-Matching (services/name_matching.py) tun wuerde - das ist eine explizite
Weisung des Nutzers, keine Aenderung an der allgemeinen Matching-Logik:

1. PwC: die 19 bestehenden "PwC GmbH WPG - <Stadt>"-Kanzleien (aus der
   116-Kanzleien-Basis) werden zu EINER einzigen Kanzlei "PwC Deutschland"
   zusammengefuehrt. Grund: die Kontakte-/Domains-CSV unterscheidet PwC
   ueberhaupt nicht nach Stadt - alle Kontakte haengen an den drei Domains
   pwc.com/pwc.de/jobalerts-de.pwc.com, eine Stadt-Zuordnung waere geraten.
   "PwC GmbH WPG - Berlin" hat als einzige der 19 echte Vertragsdaten (Status
   ACQUISITION, fee_percentage, honorar_stufe, Adresse) - sie wird deshalb als
   Basis behalten (nur umbenannt), die anderen 18 (durchweg ohne eigene
   Kontakte/Vertragsdaten) werden geloescht. Ein Kontakt
   (a.georgi@steuerberater-berlin.de, an "PwC GmbH WPG - Berlin" haengend) hat
   eine domain-fremde E-Mail (steuerberater-berlin.de) - das ist ein
   uraltes, von PwC unabhaengiges Fuzzy-Match-Artefakt (Substring-Treffer auf
   "Berlin") und wird bei dieser Gelegenheit an die tatsaechlich passende
   Kanzlei (Website-Match auf steuerberater-berlin.de) zurueckgehaengt statt
   nach "PwC Deutschland" mitgenommen zu werden.

2. ETL: die vier Domains etl-alztax.de, etl-protax.de, etl-skrok.de und
   etl-stuttgart.de wurden vom allgemeinen Fuzzy-Matching (gewollt, siehe
   test_same_brand_with_word_boundary_prefix_still_matches) in die bestehende
   Kanzlei "ETL Rechtsanwaelte GmbH" (Domain etl.de, mit echtem Vertrag)
   einsortiert. Der Nutzer will das hier NICHT - jede Domain wird zu einer
   eigenen, eigenstaendigen neuen Kanzlei (status=PROSPECT, Modell-Defaults,
   keine Vertragsdaten von "ETL Rechtsanwaelte GmbH" uebernommen - genau wie
   beim urspruenglichen Kanzlei-Domain-Import fuer neue Kanzleien). Der
   einzige tatsaechlich betroffene Kontakt (Christian.Hoffmann@etl-protax.de)
   wird von "ETL Rechtsanwaelte GmbH" zur neuen "ETL Protax" verschoben.
   "ETL Rechtsanwaelte GmbH - Berlin-Adlershof" und "Etl Pfeiffer & Kollegen
   Steuerberatungsgesellschaft Mbh" sind bereits eigenstaendig und bleiben
   unangetastet.

3. Ecovis: die bisher zusammengefuehrte "ECOVIS AG Steuerberatungsgesellschaft"
   (haelt aktuell ecovis.com + ecovis-rts.de + ecovis-kso.com) wird in genau
   drei benannte Kanzleien aufgeteilt - passend zum eigenen commercial_notes-
   Hinweis dieser Kanzlei ("ECOVIS ist ein grosses Netzwerk mit vielen
   eigenstaendigen Untergruppen ... bitte im Namen/kanzleigruppe
   praezisieren"):
     - ECOVIS       (ecovis.com)      - Basis-Datensatz, nur umbenannt,
                                         behaelt Vertragsdaten.
     - ECOVIS KSO   (ecovis-kso.com)  - neu, status=PROSPECT, Modell-Defaults,
                                         kanzleigruppe="ECOVIS" (Zugehoerigkeit
                                         zum Netzwerk, aber keine erfundenen
                                         Vertragsdaten fuer die Untergruppe).
     - RTS ECOVIS   (ecovis-rts.de)   - wie ECOVIS KSO.

Fuer alle drei Faelle gilt: E-Mail wird nach dem Kontakt-Umzug ueber
pick_client_email() ausschliesslich aus den Mailboxen/Personen der jeweils
EIGENEN Domain(s) neu berechnet (nicht mehr aus den fremden Domains, die
vorher faelschlich mitgezaehlt wurden).

Idempotent: bereits umbenannte/verschobene Datensaetze werden anhand von
Name/Website erkannt, ein zweiter Lauf aendert nichts mehr.

Ausfuehren:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\fix_pwc_etl_ecovis_20260714.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from import_kanzlei_domains_20260713 import (  # noqa: E402
    build_domain_mailboxes,
    build_domain_persons,
    load_contact_rows,
    normalize_domain,
    pick_client_email,
)

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.contact_person import ContactPerson  # noqa: E402
from cc_crm.models.enums import ClientStatus  # noqa: E402
from cc_crm.models.job_mandate import JobMandate  # noqa: E402
from cc_crm.models.submission import CandidateSubmission  # noqa: E402


def _by_website(session: Session, domain: str) -> ClientCompany | None:
    return session.query(ClientCompany).filter(ClientCompany.website == f"https://{domain}").first()


def _by_name(session: Session, name: str) -> ClientCompany | None:
    return session.query(ClientCompany).filter_by(name=name).first()


def _reassign_submissions_and_mandates(
    session: Session, source: ClientCompany, target: ClientCompany
) -> int:
    """Haengt Submissions/Mandate von source auf target um, damit source
    trotz RESTRICT-FK geloescht werden kann - fuer den PwC-Sonderfall
    ausdruecklich gewuenscht (alle Staedte-Datensaetze werden zu einer
    Kanzlei zusammengefuehrt, bestehende Prozesse/Mandate gehoeren danach
    zur zusammengefuehrten Kanzlei, nicht zu einer geloeschten Karteileiche)."""
    moved = 0
    for submission in (
        session.query(CandidateSubmission).filter_by(client_company_id=source.id).all()
    ):
        submission.client_company_id = target.id
        moved += 1
    for mandate in session.query(JobMandate).filter_by(client_company_id=source.id).all():
        mandate.client_company_id = target.id
        moved += 1
    if moved:
        session.flush()
    return moved


def _move_contact(session: Session, contact: ContactPerson, target: ClientCompany) -> None:
    contact.client_company_id = target.id
    session.flush()


def _recompute_email(
    company: ClientCompany,
    domains: list[str],
    mailboxes: dict[str, list[str]],
    persons: dict[str, list[dict[str, str]]],
) -> tuple[str | None, str | None]:
    combined_mailboxes = [email for d in domains for email in mailboxes.get(d, [])]
    combined_persons = [p for d in domains for p in persons.get(d, [])]
    old_email = company.email
    new_email, _reason = pick_client_email(combined_mailboxes, combined_persons)
    company.email = new_email
    return old_email, new_email


def fix_pwc(
    session: Session,
    mailboxes: dict[str, list[str]],
    persons: dict[str, list[dict[str, str]]],
    report: list[str],
) -> None:
    keep = _by_website(session, "pwc.com")
    if keep is None:
        keep = _by_name(session, "PwC GmbH WPG – Berlin")
    if keep is None:
        report.append("PwC: FEHLER - Basis-Kanzlei (PwC GmbH WPG - Berlin) nicht gefunden.")
        return

    old_name = keep.name
    keep.name = "PwC Deutschland"
    session.flush()

    pwc_domains = {"pwc.com", "pwc.de", "jobalerts-de.pwc.com"}
    others = (
        session.query(ClientCompany)
        .filter(ClientCompany.name.like("PwC GmbH WPG%"))
        .filter(ClientCompany.id != keep.id)
        .all()
    )

    def _relocate_contacts(company: ClientCompany) -> tuple[int, int]:
        """Verschiebt alle Kontakte von company weg: domain-eigene (pwc.*)
        nach keep, domain-fremde an die tatsaechlich passende Kanzlei (falls
        auffindbar, sonst ebenfalls nach keep). Fuer company==keep werden nur
        die domain-fremden Kontakte umgehaengt, der Rest bleibt (ist schon am
        richtigen Ziel)."""
        to_keep, elsewhere = 0, 0
        for contact in session.query(ContactPerson).filter_by(client_company_id=company.id).all():
            domain = normalize_domain((contact.email or "").rsplit("@", 1)[-1])
            if domain in pwc_domains:
                if company.id != keep.id:
                    _move_contact(session, contact, keep)
                    to_keep += 1
                continue
            target = _by_website(session, domain)
            if target is not None and target.id != company.id:
                _move_contact(session, contact, target)
                elsewhere += 1
                report.append(
                    f"  Kontakt {contact.email!r} domain-fremd -> "
                    f"{target.name!r} statt PwC Deutschland verschoben"
                )
            elif company.id != keep.id:
                _move_contact(session, contact, keep)
                to_keep += 1
        return to_keep, elsewhere

    deleted, reassigned_processes = 0, 0
    moved_to_keep, moved_elsewhere = 0, 0
    for other in others:
        to_keep, elsewhere = _relocate_contacts(other)
        moved_to_keep += to_keep
        moved_elsewhere += elsewhere

        reassigned_processes += _reassign_submissions_and_mandates(session, other, keep)
        session.delete(other)
        session.flush()
        deleted += 1

    # keep selbst kann ebenfalls domain-fremde Kontakte tragen (z.B. ein
    # Fuzzy-Match-Artefakt, das direkt an der Basis-Kanzlei haengt statt an
    # einem der 18 Duplikate - siehe Modul-Docstring, a.georgi-Beispiel).
    _, keep_elsewhere = _relocate_contacts(keep)
    moved_elsewhere += keep_elsewhere

    old_email, new_email = _recompute_email(keep, sorted(pwc_domains), mailboxes, persons)
    keep.website = "https://pwc.com"
    session.flush()

    report.append(
        f"PwC: Basis {old_name!r} -> {keep.name!r}, "
        f"{deleted} Duplikate geloescht, {reassigned_processes} Submission(s)/"
        f"Mandat(e) auf PwC Deutschland umgehaengt, {moved_to_keep} Kontakte "
        f"nach PwC Deutschland, {moved_elsewhere} domain-fremde Kontakte an "
        f"ihre richtige Kanzlei verschoben."
    )
    report.append(f"  E-Mail: {old_email!r} -> {new_email!r}")


def _ensure_standalone(
    session: Session,
    domain: str,
    name: str,
    kanzleigruppe: str | None,
    mailboxes: dict[str, list[str]],
    persons: dict[str, list[dict[str, str]]],
    report: list[str],
) -> ClientCompany:
    company = _by_website(session, domain)
    if company is None:
        company = _by_name(session, name)
    if company is None:
        company = ClientCompany(
            name=name,
            website=f"https://{domain}",
            status=ClientStatus.PROSPECT,
            kanzleigruppe=kanzleigruppe,
        )
        session.add(company)
        session.flush()
        report.append(f"  neu angelegt: {name!r} ({domain})")
    old_email, new_email = _recompute_email(company, [domain], mailboxes, persons)
    if old_email != new_email:
        report.append(f"  {name!r} E-Mail: {old_email!r} -> {new_email!r}")
    session.flush()
    return company


def fix_etl(
    session: Session,
    mailboxes: dict[str, list[str]],
    persons: dict[str, list[dict[str, str]]],
    report: list[str],
) -> None:
    base = _by_website(session, "etl.de")
    if base is None:
        base = _by_name(session, "ETL Rechtsanwälte GmbH")
    if base is None:
        report.append("ETL: FEHLER - Basis-Kanzlei (ETL Rechtsanwaelte GmbH) nicht gefunden.")
        return

    protax = _ensure_standalone(
        session, "etl-protax.de", "ETL Protax", "ETL", mailboxes, persons, report
    )
    _ensure_standalone(session, "etl-alztax.de", "ETL Alztax", "ETL", mailboxes, persons, report)
    _ensure_standalone(session, "etl-skrok.de", "ETL Skrok", "ETL", mailboxes, persons, report)
    _ensure_standalone(
        session, "etl-stuttgart.de", "ETL Stuttgart", "ETL", mailboxes, persons, report
    )

    moved = 0
    for contact in session.query(ContactPerson).filter_by(client_company_id=base.id).all():
        domain = normalize_domain((contact.email or "").rsplit("@", 1)[-1])
        if domain == "etl-protax.de":
            _move_contact(session, contact, protax)
            moved += 1

    old_email, new_email = _recompute_email(base, ["etl.de"], mailboxes, persons)
    session.flush()

    report.append(
        f"ETL: 4 Domains (alztax/protax/skrok/stuttgart) als eigenstaendige Kanzleien "
        f"sichergestellt, {moved} Kontakt(e) von {base.name!r} verschoben."
    )
    report.append(f"  {base.name!r} E-Mail: {old_email!r} -> {new_email!r}")


def fix_ecovis(
    session: Session,
    mailboxes: dict[str, list[str]],
    persons: dict[str, list[dict[str, str]]],
    report: list[str],
) -> None:
    base = _by_website(session, "ecovis.com")
    if base is None:
        base = _by_name(session, "ECOVIS AG Steuerberatungsgesellschaft")
    if base is None:
        report.append("Ecovis: FEHLER - Basis-Kanzlei nicht gefunden.")
        return

    old_name = base.name
    base.name = "ECOVIS"
    session.flush()

    kso = _ensure_standalone(
        session, "ecovis-kso.com", "ECOVIS KSO", "ECOVIS", mailboxes, persons, report
    )
    rts = _ensure_standalone(
        session, "ecovis-rts.de", "RTS ECOVIS", "ECOVIS", mailboxes, persons, report
    )

    moved_kso, moved_rts = 0, 0
    for contact in session.query(ContactPerson).filter_by(client_company_id=base.id).all():
        domain = normalize_domain((contact.email or "").rsplit("@", 1)[-1])
        if domain == "ecovis-kso.com":
            _move_contact(session, contact, kso)
            moved_kso += 1
        elif domain == "ecovis-rts.de":
            _move_contact(session, contact, rts)
            moved_rts += 1

    old_email, new_email = _recompute_email(base, ["ecovis.com"], mailboxes, persons)
    session.flush()

    report.append(
        f"Ecovis: {old_name!r} -> {base.name!r}, "
        f"{moved_kso} Kontakt(e) -> ECOVIS KSO, {moved_rts} Kontakt(e) -> RTS ECOVIS."
    )
    report.append(f"  {base.name!r} E-Mail: {old_email!r} -> {new_email!r}")


def main() -> None:
    contact_rows = load_contact_rows()
    mailboxes = build_domain_mailboxes(contact_rows)
    persons = build_domain_persons(contact_rows)

    report: list[str] = []
    session = SessionLocal()
    try:
        fix_pwc(session, mailboxes, persons, report)
        fix_etl(session, mailboxes, persons, report)
        fix_ecovis(session, mailboxes, persons, report)
        session.commit()
    finally:
        session.close()

    print("=== Zusammenfassung ===")
    for line in report:
        print(line)


if __name__ == "__main__":
    main()
