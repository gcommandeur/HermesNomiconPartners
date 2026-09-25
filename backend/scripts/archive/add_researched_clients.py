"""Legt real recherchierte Kanzlei-Standorte an bzw. taggt bestehende mit
`kanzleigruppe`, damit Netzwerk-Zugehörigkeit fürs Matching sichtbar wird.

Teil 1 - Neue Kunden (vom Nutzer benannt):
  - PWC: 25 % Honorar, 6 Monate Gewährleistung, "ganz Deutschland, jeder
    Standort" -> alle 20 offiziellen PwC-Standorte (pwc.de/de/standorte.html).
    Nur Frankfurt/München haben eine verifizierte Straßenadresse.
  - BRL (BOEGE ROHDE LUEBBEHUESEN): alle 7 per Websuche gefundenen Standorte
    (brl.de/en/offices). Honorarsatz vom Nutzer nicht genannt -> Standard 27 %
    als Platzhalter.

Teil 2 - Audit der bereits bestehenden 67 Kanzleien auf Netzwerk-Zugehörigkeit
(Nutzer-Auftrag: "prüfe für alle bereits angelegten Kanzleien die Standorte,
PKF ISSING hat ja auch 3, geh am besten immer auf die Website"):
  - Bestehende Zeilen bekommen kanzleigruppe nachgetragen (per exaktem Namen).
  - Zusätzliche real gefundene Standorte großer Netzwerke werden als neue
    Zeilen ergänzt: PKF Issing (Würzburg, Tauberbischofsheim), Auren
    (Frankfurt, Berlin), ETL Rechtsanwälte (Berlin-Adlershof), Beiten
    Burkhardt/ADVANT (Berlin, Düsseldorf, Frankfurt, Hamburg), CMS Hasche
    Sigle (Düsseldorf, Frankfurt, Hamburg, Köln, Leipzig, München, Stuttgart),
    GÖRG (Berlin, Frankfurt, Hamburg, München - nur Stadt, keine Straße
    verifiziert), WINHELLER (München - nur Stadt).
  - Bewusst NICHT ergänzt: Crowe Kleeberg (verifiziert nur 1 echter
    Standort - München), Menold Bezler (verifiziert nur 1 echter Standort -
    Stuttgart, das "8500-Kollegen-Netzwerk" ist ein internationales
    Referral-Netzwerk, keine eigenen Büros), SKNvonGEYSO (2 weitere
    Mini-Standorte nur innerhalb Hamburgs, keine Adressen verifizierbar -
    nur als Notiz vermerkt), GÖRG-Insolvenzstandorte (>20 Standorte, zu
    kleinteilig/unsicher für einzelne Zeilen).

Idempotent: prüft vor dem Anlegen, ob eine Kanzlei mit demselben Namen schon
existiert (name ist unique in der DB) und überspringt sie dann.

Ausführen:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\add_researched_clients.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.enums import ClientStatus, HonorarStufe  # noqa: E402
from cc_crm.schemas.client_company import ClientCompanyCreate  # noqa: E402
from cc_crm.services.clients import ClientCompanyService  # noqa: E402


@dataclass
class NewClient:
    name: str
    kanzleigruppe: str
    city: str
    postal_code: str | None = None
    street: str | None = None
    fee_percentage: str = "27.00"
    honorar_stufe: HonorarStufe = HonorarStufe.STANDARD
    guarantee_period_months: int = 6
    commercial_notes: str = ""
    # Ampel-Status (Nutzer-Vorgabe): grün=aktive Kundenbeziehung, gelb=in
    # Verhandlung/unklar, grau=noch keine Kundenbeziehung, rot=kein Kontakt.
    # Default PROSPECT (grau), da die meisten hier neu ergänzten Standorte
    # rein recherchiert sind, ohne tatsächlichen Kontakt - manuell im CRM
    # jederzeit änderbar, sobald sich das ändert.
    status: ClientStatus = ClientStatus.PROSPECT


# --- Teil 1: PWC ------------------------------------------------------------

PWC_NOTE_UNVERIFIED = (
    "Standort aus offizieller PwC-Standortliste (pwc.de/de/standorte.html) "
    "übernommen - Stadt/PLZ recherchiert, genaue Straßenadresse noch nicht "
    "verifiziert. Bei Bedarf im CRM ergänzen."
)
PWC_NOTE_VERIFIED = "Adresse per Websuche auf pwc.de verifiziert (Stand: Recherche-Zeitpunkt)."

PWC_CLIENTS: list[NewClient] = [
    NewClient(
        "PwC GmbH WPG – Frankfurt am Main",
        "PWC",
        "Frankfurt am Main",
        "60327",
        "Friedrich-Ebert-Anlage 35-37",
        commercial_notes=PWC_NOTE_VERIFIED,
    ),
    NewClient(
        "PwC GmbH WPG – München",
        "PWC",
        "München",
        "80636",
        "Bernhard-Wicki-Straße 8",
        commercial_notes=PWC_NOTE_VERIFIED,
    ),
    NewClient(
        "PwC GmbH WPG – Berlin", "PWC", "Berlin", "10785", commercial_notes=PWC_NOTE_UNVERIFIED
    ),
    NewClient(
        "PwC GmbH WPG – Bielefeld",
        "PWC",
        "Bielefeld",
        "33602",
        commercial_notes=PWC_NOTE_UNVERIFIED,
    ),
    NewClient(
        "PwC GmbH WPG – Bremen", "PWC", "Bremen", "28195", commercial_notes=PWC_NOTE_UNVERIFIED
    ),
    NewClient(
        "PwC GmbH WPG – Düsseldorf",
        "PWC",
        "Düsseldorf",
        "40213",
        commercial_notes=PWC_NOTE_UNVERIFIED,
    ),
    NewClient(
        "PwC GmbH WPG – Erfurt", "PWC", "Erfurt", "99084", commercial_notes=PWC_NOTE_UNVERIFIED
    ),
    NewClient(
        "PwC GmbH WPG – Essen", "PWC", "Essen", "45127", commercial_notes=PWC_NOTE_UNVERIFIED
    ),
    NewClient(
        "PwC GmbH WPG – Hamburg", "PWC", "Hamburg", "20354", commercial_notes=PWC_NOTE_UNVERIFIED
    ),
    NewClient(
        "PwC GmbH WPG – Hannover", "PWC", "Hannover", "30159", commercial_notes=PWC_NOTE_UNVERIFIED
    ),
    NewClient(
        "PwC GmbH WPG – Kassel", "PWC", "Kassel", "34117", commercial_notes=PWC_NOTE_UNVERIFIED
    ),
    NewClient("PwC GmbH WPG – Kiel", "PWC", "Kiel", "24103", commercial_notes=PWC_NOTE_UNVERIFIED),
    NewClient("PwC GmbH WPG – Köln", "PWC", "Köln", "50667", commercial_notes=PWC_NOTE_UNVERIFIED),
    NewClient(
        "PwC GmbH WPG – Leipzig", "PWC", "Leipzig", "04109", commercial_notes=PWC_NOTE_UNVERIFIED
    ),
    NewClient(
        "PwC GmbH WPG – Mannheim", "PWC", "Mannheim", "68161", commercial_notes=PWC_NOTE_UNVERIFIED
    ),
    NewClient(
        "PwC GmbH WPG – Nürnberg", "PWC", "Nürnberg", "90402", commercial_notes=PWC_NOTE_UNVERIFIED
    ),
    NewClient(
        "PwC GmbH WPG – Osnabrück",
        "PWC",
        "Osnabrück",
        "49074",
        commercial_notes=PWC_NOTE_UNVERIFIED,
    ),
    NewClient(
        "PwC GmbH WPG – Saarbrücken",
        "PWC",
        "Saarbrücken",
        "66111",
        commercial_notes=PWC_NOTE_UNVERIFIED,
    ),
    NewClient(
        "PwC GmbH WPG – Schwerin", "PWC", "Schwerin", "19053", commercial_notes=PWC_NOTE_UNVERIFIED
    ),
    NewClient(
        "PwC GmbH WPG – Stuttgart",
        "PWC",
        "Stuttgart",
        "70173",
        commercial_notes=PWC_NOTE_UNVERIFIED,
    ),
]
for _c in PWC_CLIENTS:
    _c.fee_percentage = "25.00"
    _c.honorar_stufe = (
        HonorarStufe.INDIVIDUELL
    )  # Abweichend vom Standard (27%), individuell vereinbart.
    _c.guarantee_period_months = 6
    # Gelb statt grau: reale Konditionen (25%/6 Monate) sind bekannt, aber nicht
    # klar, an welchem der 20 Standorte der tatsächliche Kontakt/Vertrag hängt
    # - "in Verhandlung oder unklar" trifft es besser als "aktive Kundenbeziehung".
    _c.status = ClientStatus.ACQUISITION

# --- Teil 1: BRL -------------------------------------------------------------

BRL_NOTE = "Adresse per Websuche auf brl.de/en/offices verifiziert (Stand: Recherche-Zeitpunkt)."
BRL_FEE_NOTE = (
    " Honorarsatz noch nicht vom Nutzer bestätigt - Standardsatz (27%) als "
    "Platzhalter, im CRM ggf. anpassen."
)
BRL_CLIENTS: list[NewClient] = [
    NewClient(
        "BRL Boege Rohde Luebbehuesen – Hamburg",
        "BRL",
        "Hamburg",
        "20355",
        "Caffamacherreihe 16",
        commercial_notes=BRL_NOTE + BRL_FEE_NOTE,
    ),
    NewClient(
        "BRL Boege Rohde Luebbehuesen – Berlin",
        "BRL",
        "Berlin",
        "10117",
        "Pariser Platz 4 A",
        commercial_notes=BRL_NOTE + BRL_FEE_NOTE,
    ),
    NewClient(
        "BRL Boege Rohde Luebbehuesen – Bochum",
        "BRL",
        "Bochum",
        "44789",
        "Meinolphusstraße 6-10",
        commercial_notes=BRL_NOTE + BRL_FEE_NOTE,
    ),
    NewClient(
        "BRL Boege Rohde Luebbehuesen – Hannover",
        "BRL",
        "Hannover",
        "30175",
        "Gellertstraße 6",
        commercial_notes=BRL_NOTE + BRL_FEE_NOTE,
    ),
    NewClient(
        "BRL Boege Rohde Luebbehuesen – Dortmund",
        "BRL",
        "Dortmund",
        "44141",
        "Lübkestraße 3",
        commercial_notes=BRL_NOTE + BRL_FEE_NOTE,
    ),
    NewClient(
        "BRL Boege Rohde Luebbehuesen – Essen",
        "BRL",
        "Essen",
        "45127",
        "Kennedyplatz 8",
        commercial_notes=BRL_NOTE + BRL_FEE_NOTE,
    ),
    NewClient(
        "BRL Boege Rohde Luebbehuesen – München",
        "BRL",
        "München",
        "80336",
        "Herzog-Heinrich-Straße 23",
        commercial_notes=BRL_NOTE + BRL_FEE_NOTE,
    ),
]
for _c in BRL_CLIENTS:
    # Gelb statt grau: Nutzer nennt BRL einen bestehenden Kunden, aber welcher
    # der 7 Standorte den tatsächlichen Kontakt hat und der Honorarsatz sind
    # unbestätigt - "in Verhandlung oder unklar" passt besser als "aktiv".
    _c.status = ClientStatus.ACQUISITION

# --- Teil 2: zusätzliche Standorte bestehender Netzwerke --------------------

NETWORK_NOTE = "Zusätzlicher Standort ergänzt beim Netzwerk-Audit bestehender Kanzleien (Websuche)."

NETWORK_EXPANSION_CLIENTS: list[NewClient] = [
    # PKF Issing Faulhaber Wozar Altenbeck - Nutzer: "hat ja auch 3"
    # (Würzburg, Tauberbischofsheim, Heilbronn=bereits vorhanden)
    NewClient(
        "PKF Issing Faulhaber Wozar Altenbeck – Würzburg",
        "PKF Issing Faulhaber Wozar Altenbeck",
        "Würzburg",
        "97070",
        "Oeggstraße 2 / Jacobi-Hof",
        commercial_notes=NETWORK_NOTE,
    ),
    NewClient(
        "PKF Issing Faulhaber Wozar Altenbeck – Tauberbischofsheim",
        "PKF Issing Faulhaber Wozar Altenbeck",
        "Tauberbischofsheim",
        commercial_notes=NETWORK_NOTE + " Straße nicht verifiziert.",
    ),
    # Auren (bestehende Zeile: "Auren Deutschland GbR", Stuttgart)
    NewClient(
        "Auren Deutschland – Frankfurt am Main",
        "Auren",
        "Frankfurt am Main",
        street="Lurgiallee 14",
        commercial_notes=NETWORK_NOTE
        + (
            " PLZ nicht verifiziert. Auren hat laut Recherche weitere Standorte "
            "u.a. in Hamburg, München, Köln, Düsseldorf, Dortmund, Leipzig, Essen, "
            "Bremen, Dresden, Hannover, Nürnberg, Duisburg - ohne verifizierte "
            "Adresse nicht als eigene Zeile angelegt."
        ),
    ),
    NewClient(
        "Auren Deutschland – Berlin",
        "Auren",
        "Berlin",
        street="Wallstraße 58/59",
        commercial_notes=NETWORK_NOTE + " PLZ nicht verifiziert.",
    ),
    # ETL Rechtsanwälte (bestehende Zeile: Berlin-Mitte 10117) - zweiter Berliner Standort
    NewClient(
        "ETL Rechtsanwälte GmbH – Berlin-Adlershof",
        "ETL",
        "Berlin",
        "12489",
        commercial_notes=NETWORK_NOTE
        + (
            " ETL ist Deutschlands größtes Steuerberatungs-/Rechtsnetzwerk "
            "(dezentral, hunderte Standorte) - nur real bekannte Standorte "
            "werden angelegt, nicht das gesamte Netzwerk."
        ),
    ),
    # Beiten Burkhardt / ADVANT Beiten (bestehende Zeile: München)
    NewClient(
        "Beiten Burkhardt (ADVANT Beiten) – Berlin",
        "Beiten Burkhardt / ADVANT Beiten",
        "Berlin",
        "10785",
        "Lützowplatz 10",
        commercial_notes=NETWORK_NOTE,
    ),
    NewClient(
        "Beiten Burkhardt (ADVANT Beiten) – Düsseldorf",
        "Beiten Burkhardt / ADVANT Beiten",
        "Düsseldorf",
        "40474",
        "Cecilienallee 7",
        commercial_notes=NETWORK_NOTE,
    ),
    NewClient(
        "Beiten Burkhardt (ADVANT Beiten) – Frankfurt am Main",
        "Beiten Burkhardt / ADVANT Beiten",
        "Frankfurt am Main",
        "60325",
        "Mainzer Landstraße 36",
        commercial_notes=NETWORK_NOTE,
    ),
    NewClient(
        "Beiten Burkhardt (ADVANT Beiten) – Hamburg",
        "Beiten Burkhardt / ADVANT Beiten",
        "Hamburg",
        "20354",
        "Neuer Wall 72",
        commercial_notes=NETWORK_NOTE,
    ),
    # CMS Hasche Sigle (bestehende Zeile: Berlin)
    NewClient(
        "CMS Hasche Sigle – Düsseldorf",
        "CMS Hasche Sigle",
        "Düsseldorf",
        "40213",
        "Kasernenstraße 43-45",
        commercial_notes=NETWORK_NOTE,
    ),
    NewClient(
        "CMS Hasche Sigle – Frankfurt am Main",
        "CMS Hasche Sigle",
        "Frankfurt am Main",
        "60311",
        "Neue Mainzer Straße 2-4",
        commercial_notes=NETWORK_NOTE,
    ),
    NewClient(
        "CMS Hasche Sigle – Hamburg",
        "CMS Hasche Sigle",
        "Hamburg",
        "20355",
        "Stadthausbrücke 1-3",
        commercial_notes=NETWORK_NOTE,
    ),
    NewClient(
        "CMS Hasche Sigle – Köln",
        "CMS Hasche Sigle",
        "Köln",
        "50678",
        "Kranhaus 1, Im Zollhafen 18",
        commercial_notes=NETWORK_NOTE,
    ),
    NewClient(
        "CMS Hasche Sigle – Leipzig",
        "CMS Hasche Sigle",
        "Leipzig",
        "04109",
        "Augustusplatz 9",
        commercial_notes=NETWORK_NOTE,
    ),
    NewClient(
        "CMS Hasche Sigle – München",
        "CMS Hasche Sigle",
        "München",
        "80335",
        "Nymphenburger Straße 12",
        commercial_notes=NETWORK_NOTE,
    ),
    NewClient(
        "CMS Hasche Sigle – Stuttgart",
        "CMS Hasche Sigle",
        "Stuttgart",
        "70173",
        "Theodor-Heuss-Straße 29",
        commercial_notes=NETWORK_NOTE,
    ),
    # GÖRG (bestehende Zeile: Köln) - nur Stadt bekannt, keine Straße verifiziert
    NewClient(
        "GÖRG Partnerschaft von Rechtsanwälten – Berlin",
        "GÖRG",
        "Berlin",
        commercial_notes=NETWORK_NOTE
        + (
            " Straße nicht verifiziert. GÖRG hat zudem >20 weitere reine "
            "Insolvenz-Standorte, die hier nicht einzeln angelegt wurden."
        ),
    ),
    NewClient(
        "GÖRG Partnerschaft von Rechtsanwälten – Frankfurt am Main",
        "GÖRG",
        "Frankfurt am Main",
        commercial_notes=NETWORK_NOTE + " Straße nicht verifiziert.",
    ),
    NewClient(
        "GÖRG Partnerschaft von Rechtsanwälten – Hamburg",
        "GÖRG",
        "Hamburg",
        commercial_notes=NETWORK_NOTE + " Straße nicht verifiziert.",
    ),
    NewClient(
        "GÖRG Partnerschaft von Rechtsanwälten – München",
        "GÖRG",
        "München",
        commercial_notes=NETWORK_NOTE + " Straße nicht verifiziert.",
    ),
    # WINHELLER (bestehende Zeile: Frankfurt am Main) - nur Stadt bekannt
    NewClient(
        "WINHELLER – München",
        "WINHELLER",
        "München",
        commercial_notes=NETWORK_NOTE
        + (
            " Straße nicht verifiziert. Quellen widersprüchlich zu weiteren "
            "Standorten (Aalen/Karlsruhe als Büro oder nur Besprechungsraum) - "
            "nicht angelegt, bei Bedarf verifizieren."
        ),
    ),
]

# Bestehende Zeilen (exakter, schon in der DB vorhandener Name) -> kanzleigruppe.
# Wird per UPDATE nachgetragen, überschreibt nichts anderes.
EXISTING_KANZLEIGRUPPE_UPDATES: dict[str, str] = {
    "Auren Deutschland GbR": "Auren",
    "PKF Issing Faulhaber Wozar Altenbeck GmbH & Co. KG Steuerberatungsgesellschaft": (
        "PKF Issing Faulhaber Wozar Altenbeck"
    ),
    "ETL Rechtsanwälte GmbH": "ETL",
    "Etl Pfeiffer & Kollegen Steuerberatungsgesellschaft Mbh": "ETL",
    "Beiten Burkhardt Rechtsanwaltsgesellschaft mbH": "Beiten Burkhardt / ADVANT Beiten",
    "CMS Hasche Sigle Partnerschaft mbB": "CMS Hasche Sigle",
    "GÖRG Partnerschaft von Rechtsanwälten mbB": "GÖRG",
    "WINHELLER GmbH": "WINHELLER",
    # Verifiziert nur 1 echter Standort - kanzleigruppe trotzdem gesetzt, damit die
    # internationale Netzwerk-Zugehörigkeit im CRM sichtbar ist (kein Multi-Standort).
    "Crowe Kleeberg GmbH": "Crowe",
    # SKNvonGEYSO hat laut Recherche 2 weitere Mini-Standorte innerhalb Hamburgs
    # (Harburg, Buchholz i.d.N.) ohne verifizierbare Adresse - nicht als eigene
    # Zeile angelegt, nur zur Kenntnis: bleibt ohne kanzleigruppe-Tag, da es sich
    # nicht um verschiedene Städte/Regionen handelt (fürs Matching irrelevant).
}


def main() -> None:
    all_new_clients = PWC_CLIENTS + BRL_CLIENTS + NETWORK_EXPANSION_CLIENTS
    session = SessionLocal()
    created = 0
    skipped_existing: list[str] = []
    failed: list[tuple[str, str]] = []
    updated_groups: list[str] = []
    not_found_for_update: list[str] = []
    try:
        service = ClientCompanyService(session)

        for entry in all_new_clients:
            existing = session.query(ClientCompany).filter_by(name=entry.name).first()
            if existing is not None:
                skipped_existing.append(entry.name)
                continue
            try:
                payload = ClientCompanyCreate(
                    name=entry.name,
                    kanzleigruppe=entry.kanzleigruppe,
                    status=entry.status,
                    street=entry.street,
                    city=entry.city,
                    postal_code=entry.postal_code,
                    fee_percentage=entry.fee_percentage,
                    honorar_stufe=entry.honorar_stufe,
                    guarantee_period_months=entry.guarantee_period_months,
                    commercial_notes=entry.commercial_notes,
                )
                service.create(payload)
                created += 1
            except Exception as exception:  # noqa: BLE001 - einzelne Zeile darf nicht alles abbrechen
                session.rollback()
                failed.append((entry.name, str(exception)))
                continue

        for name, kanzleigruppe in EXISTING_KANZLEIGRUPPE_UPDATES.items():
            row = session.query(ClientCompany).filter_by(name=name).first()
            if row is None:
                not_found_for_update.append(name)
                continue
            row.kanzleigruppe = kanzleigruppe
            updated_groups.append(name)

        session.commit()
    finally:
        session.close()

    print(f"Neu angelegt: {created}")
    print(f"Bereits vorhanden (übersprungen): {len(skipped_existing)}")
    for name in skipped_existing:
        print(f"  - {name}")
    print(f"Fehlgeschlagen: {len(failed)}")
    for name, error in failed:
        print(f"  - {name}: {error}")
    print(f"Kanzleigruppe nachgetragen bei bestehenden Zeilen: {len(updated_groups)}")
    for name in updated_groups:
        print(f"  - {name}")
    if not_found_for_update:
        print(f"Nicht gefunden (Name stimmt nicht mehr exakt überein): {len(not_found_for_update)}")
        for name in not_found_for_update:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
