"""Fuehrt doppelte ClientCompany-Datensaetze zusammen, ohne dass eine
bestehende Prozess-Verknuepfung (CandidateSubmission.client_company_id)
verloren geht.

Anlass: beim Lukas-Postfach-Import sind zwei Dubletten aufgefallen
("ClientCompany conflicts with existing data" fuer steuerberater.hamburg und
moore-intaria.de); zusaetzlich standen aus dem Audit vom 30.07.2026
(Kanzleien_Kontakte_Gmail_Abgleich_VOLLSTAENDIG_20260730.md) vier bereits
damals MANUELL BESTAETIGTE Duplikat-Paare noch offen.

ERKENNUNG - zwei Wege, beide EXAKT, KEIN Fuzzy-Namensvergleich
(bekanntes False-Positive-Risiko bei Platzhalternamen, siehe Projektnotiz
project_fuzzy_dedup_placeholder_name_risk):
  1. Live-Domain-Kollision: zwei oder mehr ClientCompany-Datensaetze, deren
     normalisierte website-/email-Domain identisch ist (normalize_domain(),
     identisch zu import_kanzleien_aus_lukas_postfach.py). Findet auch bisher
     unbekannte Faelle automatisch.
  2. Explizite, am 30.07.2026 manuell bestaetigte Paare - als exakte
     Namens-Strings in EXPLICIT_PAIRS hinterlegt, exakter String-Vergleich
     gegen ClientCompany.name, keine Aehnlichkeitsschwelle.

WICHTIG zur Abgrenzung "kein Fuzzy": Fuzzy-Logik ist fuer die ERKENNUNG von
Duplikaten verboten. Die Auswahl, WELCHER von zwei bereits als Dublette
feststehenden Datensaetzen bestehen bleibt (Keeper), ist davon unberuehrt -
dort entscheidet zuerst die Anzahl verknuepfter Submissions, danach ein
exakter Vergleich gegen den automatisch aus der Domain abgeleiteten
Platzhalternamen (siehe pick_keeper()).

KRITISCHE EINSCHRAENKUNG (Nutzer-Vorgabe, unbedingt eingehalten):
Vor dem Loeschen eines Datensatzes werden ALLE Fremdschluessel, die auf ihn
zeigen, auf den Keeper umgehaengt. Die Tabellenliste stammt nicht aus einer
Vermutung, sondern wurde gegen das DB-Schema geprueft (SQLAlchemy-Inspector:
genau 10 FKs auf client_companies.id) - siehe FK_REPOINTS. Besonders
kritisch, weil ein blosses Loeschen sonst STILL Daten zerstoert haette:
  - CASCADE (activities, contact_persons, notes, tasks) haette die Zeilen
    mitgeloescht,
  - SET NULL (calendar_events, mail_messages, email_draft_logs,
    sourcing_leads) haette sie verwaist zurueckgelassen,
  - RESTRICT (candidate_submissions, job_mandates) haette das Loeschen zwar
    blockiert, ist aber kein Ersatz fuer sauberes Umhaengen.
Zusaetzlich werden zwei WEICHE Referenzen umgehaengt, die KEIN FK schuetzt
und die deshalb bei einem naiven Merge unbemerkt ins Leere gezeigt haetten:
  - Document.owner_id mit owner_type == "client" (polymorphe Referenz,
    aktuell 135 Kanzlei-Dokumente, u.a. Vermittlungsvertraege),
  - MailingGroup.recipients (JSON-Liste mit {"kind": "client", "id": ...}).

Als letzte Sicherung wird VOR dem Loeschen erneut live gezaehlt, ob noch
irgendeine Referenz auf den Loser zeigt (verify_no_references()) - wenn ja,
wird der Loser NICHT geloescht und das Paar als Fehler protokolliert.

Weitere Regeln:
  - Nicht-leere Felder des Keepers werden NIE ueberschrieben. Nur leere
    Keeper-Felder duerfen aus dem Loser befuellt werden (FILLABLE_FIELDS).
    name/status/fee_percentage/honorar_stufe/terms_status/refund_terms/
    guarantee_period_months/payment_terms_days bleiben grundsaetzlich
    unangetastet.
    AUSNAHME: bei GENAU den zwei EXPLICIT_PAIRS-Eintraegen mit gesetztem
    website_override (Andreas Deubert, CMS Hasche Sigle) wird die
    Keeper-website zwangsweise auf die am 30.07.2026 bestaetigte Domain
    gesetzt, auch wenn dort bereits eine andere website steht - siehe
    EXPLICIT_PAIRS-Docstring fuer die Begruendung je Fall. Betrifft
    NIEMALS die generisch per Domain-Kollision erkannten Paare (Weg 1).
  - ContactPerson des Losers wird umgehaengt; bei E-Mail-Dublette
    (case-insensitive) gegen einen bereits beim Keeper vorhandenen Kontakt
    wird der Loser-Kontakt verworfen statt doppelt angelegt.
  - Alles laeuft live gegen die DB zum Ausfuehrungszeitpunkt.
  - Jeder Merge schreibt einen AuditLog-Eintrag (action="merged_into"),
    analog zum "deleted"-Eintrag in services/clients.py::delete.

Goetz & Partner mbB ist laut Auftrag KEIN Duplikat, sondern nur eine
fehlende Domain - wird separat behandelt (nur website befuellen, falls
leer), siehe DOMAIN_ONLY_FIXES.

!!! ACHTUNG: --apply schreibt echt in die Datenbank. Bitte VORHER ein
Datenbank-Backup ueber die DO-Console ausgefuehrt haben. !!!

Usage (aus backend/, ueber die DO-App-Platform-Console des Backend-
Containers):

    python scripts/merge_kanzlei_duplikate.py
    python scripts/merge_kanzlei_duplikate.py --apply
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

from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.activity import Activity  # noqa: E402
from cc_crm.models.calendar_event import CalendarEvent  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.contact_person import ContactPerson  # noqa: E402
from cc_crm.models.job_mandate import JobMandate  # noqa: E402
from cc_crm.models.mail import MailMessage  # noqa: E402
from cc_crm.models.mailing_group import MailingGroup  # noqa: E402
from cc_crm.models.note import Note  # noqa: E402
from cc_crm.models.operational import Document, EmailDraftLog  # noqa: E402
from cc_crm.models.recruiting import AuditLog  # noqa: E402
from cc_crm.models.sourcing_lead import SourcingLead  # noqa: E402
from cc_crm.models.submission import CandidateSubmission  # noqa: E402
from cc_crm.models.task import Task  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "merge_kanzlei_duplikate_review.csv"

CSV_FIELDS = [
    "keeper_id",
    "keeper_name",
    "loser_id",
    "loser_name",
    "domain_oder_grund",
    "submissions_umgehaengt",
    "contacts_umgehaengt",
    "contacts_verworfen_dubletten",
    "felder_befuellt",
    "aktion",
    "error",
    # Zusatzspalte ueber die Auftragsvorgabe hinaus: markiert Paare, bei denen
    # die Domains der beiden Seiten NICHT uebereinstimmen (nur bei den
    # expliziten Paaren moeglich). Rein informativ, beeinflusst den Merge
    # nicht - siehe Abschlussbericht.
    "warnung",
]

# Alle 10 echten Fremdschluessel auf client_companies.id, gegen das
# DB-Schema verifiziert (SQLAlchemy-Inspector). ContactPerson steht bewusst
# NICHT hier, weil dort zusaetzlich die E-Mail-Dubletten-Pruefung noetig ist
# (siehe repoint_contacts()).
FK_REPOINTS: list[tuple[type, str, str]] = [
    (CandidateSubmission, "client_company_id", "candidate_submissions"),
    (Activity, "client_company_id", "activities"),
    (CalendarEvent, "client_company_id", "calendar_events"),
    (EmailDraftLog, "client_company_id", "email_draft_logs"),
    (JobMandate, "client_company_id", "job_mandates"),
    (MailMessage, "matched_client_company_id", "mail_messages"),
    (Note, "client_company_id", "notes"),
    (SourcingLead, "matched_client_company_id", "sourcing_leads"),
    (Task, "client_company_id", "tasks"),
]

# Felder, die auf dem Keeper aus dem Loser befuellt werden duerfen - aber NUR
# wenn sie beim Keeper leer sind. Bewusst NICHT enthalten: name, status,
# fee_percentage, honorar_stufe, terms_status, refund_terms,
# guarantee_period_months, payment_terms_days (Nutzer-Vorgabe: nie anfassen;
# sind ohnehin non-nullable mit Default, also nie wirklich "leer").
FILLABLE_FIELDS = [
    "kanzleigruppe",
    "website",
    "email",
    "phone",
    "street",
    "postal_code",
    "city",
    "region",
    "company_size",
    "focus",
    "linkedin_url",
    "last_contact_at",
    "next_follow_up_at",
    "nachlass_begruendung",
    "agb_version",
    "special_terms",
    "commercial_notes",
    "notes",
    "owner_user_id",
]

# Am 30.07.2026 manuell bestaetigte Paare (keeper_name, loser_name,
# website_override) - exakte String-Vergleiche gegen ClientCompany.name,
# keine Aehnlichkeitsschwelle.
#
# website_override: bei den meisten Paaren None (die generische "nur leere
# Keeper-Felder befuellen"-Regel reicht). Bei genau zwei Paaren wurde die
# korrekte Domain am 30.07.2026 bereits per echter Korrespondenz bestaetigt
# UND weicht von der aktuell beim Keeper hinterlegten (falschen) website ab -
# dort erzwingt der Override das Ueberschreiben einer NICHT-leeren
# Keeper-website, exklusiv fuer diese beiden Paare (siehe merge_pair()):
#   - CMS Hasche Sigle: Keeper-website s-h-partner.de war laut Audit
#     "vermutlich falsch" (keine Korrespondenz gefunden) - cms-hs.com ist
#     die bestaetigte, richtige Domain.
#   - Andreas Deubert: stb-deubert.de wurde durch echte Korrespondenz
#     (kanzlei@stb-deubert.de) bestaetigt.
EXPLICIT_PAIRS: list[tuple[str, str, str | None]] = [
    (
        # Voller Name inkl. "Partnerschaft mbB" - live gegen Prod bestaetigt
        # (der urspruenglich hinterlegte, kuerzere String traf weder lokal
        # noch in Prod einen echten Datensatz und liess das Paar deshalb
        # sauber, aber ungewollt uebersprungen).
        "Menold Bezler Rechtsanwälte Steuerberater Wirtschaftsprüfer Partnerschaft mbB",
        "Menoldbezler",
        None,
    ),
    (
        "Andreas Deubert Steuerberater · Diplom-Kaufmann",
        "Stb Deubert",
        "stb-deubert.de",
    ),
    ("CMS Hasche Sigle Partnerschaft mbB", "Cms Hs", "cms-hs.com"),
]

# Kein Duplikat, nur fehlende Domain nachtragen (Auftrag): (name, domain).
DOMAIN_ONLY_FIXES: list[tuple[str, str]] = [
    ("Götz & Partner mbB", "goetz-partner.de"),
]


def normalize_domain(value: str | None) -> str:
    """Identisch zu import_kanzleien_aus_lukas_postfach.py::normalize_domain."""
    value = (value or "").strip().lower()
    if "://" in value:
        value = urlparse(value).netloc or value
    value = value.removeprefix("www.")
    return value.rstrip("/")


def derive_name_from_domain(domain: str) -> str:
    """Identisch zu import_kanzleien_aus_lukas_postfach.py - erzeugt genau den
    Platzhalternamen, den das Import-Skript vergeben hat, wenn kein echter
    Firmenname bekannt war ("alt-partner.de" -> "Alt Partner"). Damit laesst
    sich per EXAKTEM Stringvergleich feststellen, welcher von zwei
    Datensaetzen der automatisch erzeugte Platzhalter ist - ohne Fuzzy-
    Logik."""
    base = domain.split(".")[0]
    base = base.replace("-", " ").replace("_", " ")
    return base.title() or domain


def company_domains(client: ClientCompany) -> set[str]:
    domains: set[str] = set()
    if client.website:
        domains.add(normalize_domain(client.website))
    if client.email and "@" in client.email:
        domains.add(normalize_domain(client.email.split("@", 1)[1]))
    return {domain for domain in domains if domain}


def submission_count(session: Session, client_id: uuid.UUID) -> int:
    return (
        session.query(CandidateSubmission)
        .filter(CandidateSubmission.client_company_id == client_id)
        .count()
    )


def pick_keeper(
    session: Session, candidates: list[ClientCompany], domain: str | None
) -> tuple[ClientCompany, list[ClientCompany]]:
    """Bestimmt den bleibenden Datensatz. Reihenfolge (Nutzer-Vorgabe):
    1. meiste verknuepfte CandidateSubmission-Zeilen,
    2. bei Gleichstand: der Datensatz, dessen Name NICHT exakt dem aus der
       Domain abgeleiteten Platzhalternamen entspricht (exakter Vergleich,
       siehe derive_name_from_domain),
    3. danach: mehr Wortbestandteile im Namen (ein Platzhalter ist typisch
       ein bis zwei generische Woerter),
    4. zuletzt: aeltester Datensatz (created_at) - rein deterministischer
       Tiebreak, damit das Ergebnis reproduzierbar ist."""
    placeholder = derive_name_from_domain(domain) if domain else None

    def sort_key(client: ClientCompany) -> tuple[int, int, int, str]:
        subs = submission_count(session, client.id)
        is_placeholder = 1 if placeholder is not None and client.name == placeholder else 0
        return (
            -subs,
            is_placeholder,
            -len(client.name.split()),
            client.created_at.isoformat() if client.created_at else "",
        )

    ordered = sorted(candidates, key=sort_key)
    return ordered[0], ordered[1:]


def count_references(session: Session, client_id: uuid.UUID) -> dict[str, int]:
    """Zaehlt live ALLE Referenzen auf einen ClientCompany-Datensatz - harte
    FKs, die polymorphe Document-Referenz und die JSON-Referenz in
    MailingGroup.recipients. Wird zweimal benutzt: fuer den Dry-Run-Bericht
    und als Sicherung unmittelbar vor dem Loeschen."""
    counts: dict[str, int] = {}
    for model, attr, label in FK_REPOINTS:
        counts[label] = session.query(model).filter(getattr(model, attr) == client_id).count()
    counts["contact_persons"] = (
        session.query(ContactPerson)
        .filter(ContactPerson.client_company_id == client_id)
        .count()
    )
    counts["documents"] = (
        session.query(Document)
        .filter(Document.owner_type == "client", Document.owner_id == client_id)
        .count()
    )
    mailing_hits = 0
    for group in session.query(MailingGroup).all():
        for recipient in group.recipients or []:
            if recipient.get("kind") == "client" and str(recipient.get("id")) == str(client_id):
                mailing_hits += 1
    counts["mailing_groups"] = mailing_hits
    return counts


def repoint_contacts(
    session: Session, keeper: ClientCompany, loser: ClientCompany, *, apply: bool
) -> tuple[int, int]:
    """Haengt die Kontakte des Losers auf den Keeper um. Kontakte, deren
    E-Mail (case-insensitive) beim Keeper schon existiert, werden verworfen
    statt doppelt angelegt. Gibt (umgehaengt, verworfen) zurueck."""
    keeper_emails = {
        contact.email.strip().lower()
        for contact in session.query(ContactPerson)
        .filter(ContactPerson.client_company_id == keeper.id)
        .all()
        if contact.email
    }
    loser_contacts = (
        session.query(ContactPerson)
        .filter(ContactPerson.client_company_id == loser.id)
        .all()
    )

    moved = 0
    dropped = 0
    for contact in loser_contacts:
        email = contact.email.strip().lower() if contact.email else None
        if email and email in keeper_emails:
            dropped += 1
            if apply:
                session.delete(contact)
            continue
        moved += 1
        if email:
            keeper_emails.add(email)
        if apply:
            contact.client_company_id = keeper.id
    return moved, dropped


def repoint_mailing_groups(
    session: Session, keeper_id: uuid.UUID, loser_id: uuid.UUID, *, apply: bool
) -> int:
    """MailingGroup.recipients ist eine JSON-Liste ohne FK - ein Merge muss
    die Loser-ID dort ebenfalls ersetzen, sonst zeigt der Eintrag nach dem
    Loeschen ins Leere (kein DB-Fehler, faellt also sonst nie auf)."""
    changed = 0
    for group in session.query(MailingGroup).all():
        recipients = group.recipients or []
        hit = False
        for recipient in recipients:
            if recipient.get("kind") == "client" and str(recipient.get("id")) == str(loser_id):
                hit = True
                changed += 1
                if apply:
                    recipient["id"] = str(keeper_id)
        if hit and apply:
            group.recipients = recipients
            flag_modified(group, "recipients")
    return changed


def fill_empty_fields(keeper: ClientCompany, loser: ClientCompany, *, apply: bool) -> list[str]:
    """Befuellt ausschliesslich LEERE Keeper-Felder aus dem Loser. Ein
    nicht-leeres Keeper-Feld wird nie ueberschrieben (Nutzer-Vorgabe)."""
    filled: list[str] = []
    for field in FILLABLE_FIELDS:
        keeper_value = getattr(keeper, field, None)
        loser_value = getattr(loser, field, None)
        keeper_empty = keeper_value is None or (
            isinstance(keeper_value, str) and not keeper_value.strip()
        )
        loser_has = loser_value is not None and not (
            isinstance(loser_value, str) and not loser_value.strip()
        )
        if keeper_empty and loser_has:
            filled.append(field)
            if apply:
                setattr(keeper, field, loser_value)
    return filled


def merge_pair(
    session: Session,
    keeper: ClientCompany,
    loser: ClientCompany,
    grund: str,
    *,
    apply: bool,
    website_override: str | None = None,
) -> dict[str, object]:
    """Fuehrt EIN Paar zusammen. Reihenfolge ist sicherheitsrelevant: erst
    alle Referenzen umhaengen, dann Felder befuellen (Override zuerst, dann
    die generische Nur-leere-Felder-Logik), dann live verifizieren, dass
    nichts mehr auf den Loser zeigt - und erst danach loeschen.

    website_override: NUR fuer die zwei explizit am 30.07.2026 bestaetigten
    Paare gesetzt (siehe EXPLICIT_PAIRS-Docstring) - erzwingt das
    Ueberschreiben einer bereits gesetzten, NICHT-leeren Keeper-website mit
    der bestaetigten, korrekten Domain. Bei der generischen Domain-Kollision-
    Erkennung (Weg 1) bleibt die "nie nicht-leere Felder ueberschreiben"-
    Regel unangetastet - dort ist website_override immer None."""
    row: dict[str, object] = {
        "keeper_id": str(keeper.id),
        "keeper_name": keeper.name,
        "loser_id": str(loser.id),
        "loser_name": loser.name,
        "domain_oder_grund": grund,
        "submissions_umgehaengt": 0,
        "contacts_umgehaengt": 0,
        "contacts_verworfen_dubletten": 0,
        "felder_befuellt": "",
        "aktion": "",
        "error": "",
        "warnung": "",
    }

    keeper_domains = company_domains(keeper)
    loser_domains = company_domains(loser)
    if (
        website_override is None
        and keeper_domains
        and loser_domains
        and not (keeper_domains & loser_domains)
    ):
        row["warnung"] = (
            f"Domains weichen ab (Keeper: {sorted(keeper_domains)}, "
            f"Loser: {sorted(loser_domains)}) - vor --apply pruefen"
        )

    override_note = ""
    if website_override is not None:
        override_url = f"https://{website_override}"
        if keeper.website != override_url:
            override_note = f"website (ueberschrieben: {keeper.website!r} -> {override_url!r})"
            if apply:
                keeper.website = override_url

    before = count_references(session, loser.id)
    row["submissions_umgehaengt"] = before["candidate_submissions"]

    for model, attr, label in FK_REPOINTS:
        if apply:
            session.query(model).filter(getattr(model, attr) == loser.id).update(
                {attr: keeper.id}, synchronize_session=False
            )
        del label

    moved, dropped = repoint_contacts(session, keeper, loser, apply=apply)
    row["contacts_umgehaengt"] = moved
    row["contacts_verworfen_dubletten"] = dropped

    if apply:
        session.query(Document).filter(
            Document.owner_type == "client", Document.owner_id == loser.id
        ).update({"owner_id": keeper.id}, synchronize_session=False)
    repoint_mailing_groups(session, keeper.id, loser.id, apply=apply)

    filled = fill_empty_fields(keeper, loser, apply=apply)
    if override_note:
        filled = [override_note, *filled]
    row["felder_befuellt"] = ",".join(filled)

    if not apply:
        row["aktion"] = "WUERDE MERGEN"
        return row

    session.flush()

    # Sicherung: nach dem Umhaengen darf NICHTS mehr auf den Loser zeigen.
    remaining = {
        label: count for label, count in count_references(session, loser.id).items() if count
    }
    if remaining:
        session.rollback()
        row["aktion"] = "FEHLER"
        row["error"] = f"Nach Umhaengen zeigen noch Referenzen auf den Loser: {remaining}"
        return row

    session.add(
        AuditLog(
            entity_type="client_company",
            entity_id=loser.id,
            action="merged_into",
            changed_by="scripts/merge_kanzlei_duplikate.py",
            old_values={"name": loser.name, "kanzleigruppe": loser.kanzleigruppe},
            new_values={"merged_into_id": str(keeper.id), "merged_into_name": keeper.name},
        )
    )
    session.delete(loser)
    session.commit()
    row["aktion"] = "GEMERGT"
    return row


def find_domain_collisions(session: Session) -> list[tuple[str, list[ClientCompany]]]:
    """Erkennungsweg 1: identische normalisierte website-/email-Domain."""
    index: dict[str, list[ClientCompany]] = {}
    for client in session.query(ClientCompany).all():
        for domain in company_domains(client):
            index.setdefault(domain, []).append(client)
    return [(domain, clients) for domain, clients in sorted(index.items()) if len(clients) > 1]


def run(*, apply: bool) -> tuple[dict[str, int], list[dict[str, object]]]:
    stats = {
        "pairs_domain": 0,
        "pairs_explicit": 0,
        "merged": 0,
        "skipped": 0,
        "domain_only_fixed": 0,
        "errors": 0,
    }
    rows: list[dict[str, object]] = []

    with SessionLocal() as session:
        processed: set[uuid.UUID] = set()

        # --- Erkennungsweg 1: Domain-Kollision ---
        for domain, clients in find_domain_collisions(session):
            keeper, losers = pick_keeper(session, clients, domain)
            for loser in losers:
                if loser.id in processed or keeper.id == loser.id:
                    continue
                stats["pairs_domain"] += 1
                row = merge_pair(session, keeper, loser, f"Domain-Kollision: {domain}", apply=apply)
                processed.add(loser.id)
                rows.append(row)
                if row["aktion"] == "GEMERGT":
                    stats["merged"] += 1
                elif row["aktion"] == "FEHLER":
                    stats["errors"] += 1

        # --- Erkennungsweg 2: explizit bestaetigte Paare ---
        for keeper_name, loser_name, website_override in EXPLICIT_PAIRS:
            named_keeper = (
                session.query(ClientCompany).filter(ClientCompany.name == keeper_name).first()
            )
            named_loser = (
                session.query(ClientCompany).filter(ClientCompany.name == loser_name).first()
            )
            grund = f"Manuell bestaetigt 30.07.2026: {loser_name!r} -> {keeper_name!r}"

            if named_keeper is None or named_loser is None:
                stats["skipped"] += 1
                fehlend = "Keeper" if named_keeper is None else "Loser"
                rows.append(
                    {
                        "keeper_id": str(named_keeper.id) if named_keeper else "",
                        "keeper_name": keeper_name,
                        "loser_id": str(named_loser.id) if named_loser else "",
                        "loser_name": loser_name,
                        "domain_oder_grund": grund,
                        "submissions_umgehaengt": 0,
                        "contacts_umgehaengt": 0,
                        "contacts_verworfen_dubletten": 0,
                        "felder_befuellt": "",
                        "aktion": (
                            f"UEBERSPRUNGEN ({fehlend}-Datensatz mit exaktem Namen nicht gefunden)"
                        ),
                        "error": "",
                        "warnung": "",
                    }
                )
                continue

            if named_keeper.id == named_loser.id or named_loser.id in processed:
                stats["skipped"] += 1
                rows.append(
                    {
                        "keeper_id": str(named_keeper.id),
                        "keeper_name": named_keeper.name,
                        "loser_id": str(named_loser.id),
                        "loser_name": named_loser.name,
                        "domain_oder_grund": grund,
                        "submissions_umgehaengt": 0,
                        "contacts_umgehaengt": 0,
                        "contacts_verworfen_dubletten": 0,
                        "felder_befuellt": "",
                        "aktion": "UEBERSPRUNGEN (bereits ueber Domain-Kollision verarbeitet)",
                        "error": "",
                        "warnung": "",
                    }
                )
                continue

            stats["pairs_explicit"] += 1
            row = merge_pair(
                session,
                named_keeper,
                named_loser,
                grund,
                apply=apply,
                website_override=website_override,
            )
            processed.add(named_loser.id)
            rows.append(row)
            if row["aktion"] == "GEMERGT":
                stats["merged"] += 1
            elif row["aktion"] == "FEHLER":
                stats["errors"] += 1

        # --- Sonderfall: nur fehlende Domain nachtragen, KEIN Merge ---
        for name, domain in DOMAIN_ONLY_FIXES:
            client = session.query(ClientCompany).filter(ClientCompany.name == name).first()
            base = {
                "keeper_id": str(client.id) if client else "",
                "keeper_name": name,
                "loser_id": "",
                "loser_name": "",
                "domain_oder_grund": f"Nur Domain-Ergaenzung (kein Duplikat): {domain}",
                "submissions_umgehaengt": 0,
                "contacts_umgehaengt": 0,
                "contacts_verworfen_dubletten": 0,
                "felder_befuellt": "",
                "error": "",
                "warnung": "",
            }
            if client is None:
                stats["skipped"] += 1
                rows.append({**base, "aktion": "UEBERSPRUNGEN (Kanzlei nicht gefunden)"})
                continue
            if client.website and client.website.strip():
                stats["skipped"] += 1
                rows.append(
                    {
                        **base,
                        "aktion": f"UEBERSPRUNGEN (website bereits gesetzt: {client.website})",
                    }
                )
                continue
            if apply:
                client.website = f"https://{domain}"
                session.commit()
            stats["domain_only_fixed"] += 1
            rows.append(
                {
                    **base,
                    "felder_befuellt": "website",
                    "aktion": "WEBSITE ERGAENZT" if apply else "WUERDE WEBSITE ERGAENZEN",
                }
            )

    return stats, rows


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
    print(f"=== Kanzlei-Duplikate zusammenfuehren ({mode}) ===\n")

    stats, rows = run(apply=args.apply)
    _write_review_csv(rows)

    print("\n=== Zusammenfassung ===")
    print(f"Duplikat-Paare ueber Domain-Kollision (Weg 1): {stats['pairs_domain']}")
    print(f"Duplikat-Paare ueber explizite Liste (Weg 2): {stats['pairs_explicit']}")
    verb = "Gemergte Paare" if args.apply else "Paare, die gemergt wuerden"
    merged_count = (
        stats["merged"]
        if args.apply
        else stats["pairs_domain"] + stats["pairs_explicit"] - stats["errors"]
    )
    print(f"{verb}: {merged_count}")
    print(f"Übersprungen (kein echtes Duplikat / nicht gefunden): {stats['skipped']}")
    fix_verb = "Domain ergaenzt" if args.apply else "Domain wuerde ergaenzt"
    print(f"{fix_verb} (Goetz & Partner, kein Merge): {stats['domain_only_fixed']}")
    print(f"Fehler: {stats['errors']}")
    print(f"\nReview-CSV: {OUTPUT_PATH}")

    warnings = [row for row in rows if row.get("warnung")]
    if warnings:
        print(f"\n!!! {len(warnings)} Paar(e) mit abweichenden Domains - bitte pruefen:")
        for row in warnings:
            print(f"  - {row['loser_name']!r} -> {row['keeper_name']!r}: {row['warnung']}")

    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Review-CSV prüfen, dann mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
