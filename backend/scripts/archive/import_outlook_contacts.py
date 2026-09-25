"""Importiert Kanzlei-/Kunden-Kontakte aus dem Outlook-Postfach
info@commandeurconsulting.de (Nutzer-Auftrag: "aus meinen outlook mails die
kontakte herziehen"). Nutzer-Entscheidungen dazu:
  - Zeitraum: gesamter Verlauf (Nutzer: "Gesamter Verlauf und es sind mehrere
    Mails, ich habe IMAP Mails").
  - Kontakte ohne passende bestehende Kanzlei: neue Kanzlei anlegen (Nutzer:
    "Hierzu sollen neue Kanzleien erstellt werden.").

Wichtiger Hinweis zum Umfang: Über die verbundene Microsoft-Graph-Anbindung
ist nur das Postfach info@commandeurconsulting.de erreichbar (33 Mails Posteingang
+ 38 Mails Gesendet = 71 Mails, komplett gesichtet). Der Nutzer erwähnte
zusätzliche IMAP-Postfächer ("ich habe IMAP Mails") - diese sind über die
aktuell verbundene Anbindung NICHT erreichbar und wurden hier NICHT
durchsucht. Für weitere Postfächer müsste ein zusätzlicher Connector verbunden
werden.

Ergebnis der Sichtung (71 Mails): der allergrößte Teil ist internes
Test-Rauschen (interne Testmails, Zustellfehler, Newsletter/Spam von
Hunter.io/Microsoft/McAfee/XING). Echte externe Geschäftskontakte mit Kanzlei-/
Kundenbezug:
  1. BÄUERLE Steuerberatungsgesellschaft mbH, Stuttgart - NEU, nicht in den
     bestehenden 67 Kanzleien. Kontakt: bewerbung@baeuerle-steuerberater.de
     ("Frau Bührer", laut Anrede in der Mail). Adresse per Websuche verifiziert
     (baeuerle-steuerberater.de/kanzlei/kontakt.html).
  2. BAUER KOMPRESSOREN GmbH - bereits als Kanzlei/Kunde vorhanden (München).
     2 neue Kontakte aus einer Interview-Koordinations-Mail (a.deierer@,
     v.sandfuchs@ auf bauer-kompressoren.de) + 2 auf der Konzern-Domain
     bauergroup.com (d.gebele@, m.ruf@) - alle im selben Fadenzusammenhang
     (Interview Frau Misaleva), daher an denselben bestehenden Datensatz
     gehängt.
  3. VidaCura GmbH - bereits als Kanzlei/Kunde vorhanden (München). 1 neuer
     Kontakt: fritz@vidacura.de.

NICHT automatisch angelegt (Ambiguität, zur manuellen Prüfung im Skript-Output
markiert): a.huber@rotorcomp.de (Rotorcomp) - taucht nur einmal auf, unklar ob
eigenständiger Kunde oder nur ein Ansprechpartner im selben Bauer-Group-Umfeld.

Namenshinweis: Vor-/Nachname wurde, wo nicht aus dem Mailtext ersichtlich, nur
aus dem E-Mail-Lokalteil abgeleitet (z.B. "v.sandfuchs" -> Vorname "V.",
Nachname "Sandfuchs") - das ist eine Vermutung, keine verifizierte Schreibweise,
bei Bedarf im CRM korrigieren.

Idempotent: prüft vor dem Anlegen, ob eine Kanzlei mit demselben Namen bzw. ein
Kontakt mit derselben E-Mail schon existiert.

Ausführen:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\import_outlook_contacts.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.contact_person import ContactPerson  # noqa: E402
from cc_crm.models.enums import ClientStatus  # noqa: E402
from cc_crm.schemas.client_company import ClientCompanyCreate  # noqa: E402
from cc_crm.schemas.contact_person import ContactPersonCreate  # noqa: E402
from cc_crm.services.clients import ClientCompanyService  # noqa: E402
from cc_crm.services.contacts import ContactPersonService  # noqa: E402


@dataclass
class NewContact:
    first_name: str
    last_name: str
    email: str
    role_title: str | None = None
    is_primary: bool = False


NEW_CLIENT_NAME = "BÄUERLE Steuerberatungsgesellschaft mbH"

BAEUERLE_CONTACTS = [
    NewContact(
        "(unbekannt)",
        "Bührer",
        "bewerbung@baeuerle-steuerberater.de",
        "Bewerbungen/Rekrutierung (aus Outlook-Verlauf)",
        is_primary=True,
    ),
]

# Kontakte für bereits bestehende Kanzleien/Kunden - Zuordnung per exaktem,
# bereits in der DB vorhandenem Namen.
EXISTING_CLIENT_CONTACTS: dict[str, list[NewContact]] = {
    "BAUER KOMPRESSOREN GmbH": [
        NewContact(
            "A.",
            "Deierer",
            "a.deierer@bauer-kompressoren.de",
            "Aus Outlook-Verlauf (Interview-Koordination)",
        ),
        NewContact(
            "V.",
            "Sandfuchs",
            "v.sandfuchs@bauer-kompressoren.de",
            "Aus Outlook-Verlauf (Interview-Koordination)",
        ),
        NewContact(
            "D.",
            "Gebele",
            "d.gebele@bauergroup.com",
            "Aus Outlook-Verlauf (bauergroup.com - Konzernebene)",
        ),
        NewContact(
            "M.",
            "Ruf",
            "m.ruf@bauergroup.com",
            "Aus Outlook-Verlauf (bauergroup.com - Konzernebene)",
        ),
    ],
    "VidaCura GmbH": [
        NewContact("Fritz", "(unbekannt)", "fritz@vidacura.de", "Aus Outlook-Verlauf"),
    ],
}

# Nicht automatisch angelegt - nur zur Kenntnis im Report.
FLAGGED_FOR_REVIEW = [
    "a.huber@rotorcomp.de (Rotorcomp) - taucht nur 1x auf, unklare Kanzlei-/Kundenzuordnung, "
    "manuell prüfen ob eigener Kunde oder nur Kontakt im Bauer-Group-Umfeld."
]


def main() -> None:
    session = SessionLocal()
    created_clients = 0
    created_contacts: list[str] = []
    skipped_contacts: list[str] = []
    failed: list[tuple[str, str]] = []
    try:
        client_service = ClientCompanyService(session)
        contact_service = ContactPersonService(session)

        # 1) Neue Kanzlei: Bäuerle
        baeuerle = session.query(ClientCompany).filter_by(name=NEW_CLIENT_NAME).first()
        if baeuerle is None:
            try:
                baeuerle = client_service.create(
                    ClientCompanyCreate(
                        name=NEW_CLIENT_NAME,
                        status=ClientStatus.ACQUISITION,
                        street="Grüninger Straße 5",
                        city="Stuttgart",
                        postal_code="70599",
                        commercial_notes=(
                            "Über Outlook-Kontaktabgleich gefunden (Bewerbungsprozess K-Nr. 4001, "
                            "Steuerberaterin in Stuttgart). Adresse per Websuche verifiziert "
                            "(baeuerle-steuerberater.de)."
                        ),
                    )
                )
                created_clients += 1
            except Exception as exception:  # noqa: BLE001
                session.rollback()
                failed.append((NEW_CLIENT_NAME, str(exception)))
                baeuerle = None

        if baeuerle is not None:
            for contact in BAEUERLE_CONTACTS:
                _create_contact_if_new(
                    session,
                    contact_service,
                    baeuerle.id,
                    contact,
                    created_contacts,
                    skipped_contacts,
                    failed,
                )

        # 2) Kontakte an bestehende Kanzleien hängen
        for client_name, contacts in EXISTING_CLIENT_CONTACTS.items():
            client = session.query(ClientCompany).filter_by(name=client_name).first()
            if client is None:
                failed.append(
                    (
                        client_name,
                        "Bestehende Kanzlei nicht gefunden - Name stimmt nicht mehr exakt überein.",
                    )
                )
                continue
            for contact in contacts:
                _create_contact_if_new(
                    session,
                    contact_service,
                    client.id,
                    contact,
                    created_contacts,
                    skipped_contacts,
                    failed,
                )

        session.commit()
    finally:
        session.close()

    print(f"Neue Kanzleien angelegt: {created_clients}")
    print(f"Neue Kontakte angelegt: {len(created_contacts)}")
    for name in created_contacts:
        print(f"  - {name}")
    print(f"Bereits vorhanden (übersprungen, gleiche E-Mail): {len(skipped_contacts)}")
    for name in skipped_contacts:
        print(f"  - {name}")
    print(f"Fehlgeschlagen: {len(failed)}")
    for name, error in failed:
        print(f"  - {name}: {error}")
    print(f"Zur manuellen Prüfung markiert (nicht automatisch angelegt): {len(FLAGGED_FOR_REVIEW)}")
    for note in FLAGGED_FOR_REVIEW:
        print(f"  - {note}")


def _create_contact_if_new(
    session, contact_service, client_id, contact: NewContact, created, skipped, failed
) -> None:
    existing = session.query(ContactPerson).filter_by(email=contact.email).first()
    if existing is not None:
        skipped.append(contact.email)
        return
    try:
        contact_service.create(
            ContactPersonCreate(
                client_company_id=client_id,
                first_name=contact.first_name,
                last_name=contact.last_name,
                email=contact.email,
                role_title=contact.role_title,
                is_primary=contact.is_primary,
            )
        )
        created.append(f"{contact.first_name} {contact.last_name} <{contact.email}>")
    except Exception as exception:  # noqa: BLE001
        session.rollback()
        failed.append((contact.email, str(exception)))


if __name__ == "__main__":
    main()
