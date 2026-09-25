"""Behebt zwei Datenqualitaets-Probleme bei ContactPerson, die Gegë per
Live-API-Abzug und eigener Analyse aller 1260 Kontakte gefunden hat
(Auftrag "Kontakte-Datenqualitaet: Analyse + Bereinigungsauftrag",
2026-09-16):

1. NAME-SPLIT (71 Kontakte + 1 Sonderfall): first_name ist leer, last_name
   traegt noch das unverarbeitete "vorname.nachname"-Muster aus der
   urspruenglichen E-Mail-Adress-Extraktion (vorname.nachname@domain.de
   wurde nie in first_name/last_name aufgesplittet). NAME_SPLITS unten
   enthaelt die von Gegë manuell prtueften Ziel-Werte fuer jede ID - dieses
   Skript uebernimmt sie nur, PRUEFT aber live den aktuellen Stand jeder
   Zeile vor dem Schreiben (siehe apply_name_splits) und bricht bei einer
   unerwarteten Abweichung (z.B. bereits von jemand anderem bearbeitet)
   NICHT automatisch durch, sondern meldet sie zur manuellen Pruefung.
   Sonderfall 4ce31ff5-...: kein vorname.nachname-Muster, sondern ein
   generisches mail@-Funktionspostfach (mail.nordheide@kanzlei-bns.de) -
   first_name bleibt leer, nur last_name wird auf "Nordheide" bereinigt.

2. DUBLETTEN (3 Kontakte): jeweils zwei ContactPerson-Zeilen fuer dieselbe
   Person, entstanden durch eine "graue" Duplikat-Kanzlei aus dem
   12.09.2026-Mail-Import (siehe Nutzer-Hinweis: das deutet auf weitere,
   noch nicht per Kontakt-Kollision aufgefallene Duplikat-Kanzleien hin -
   separater Folgeauftrag, NICHT Teil dieses Skripts). Vor dem Loeschen des
   jeweils aermeren Duplikats werden ALLE Referenzen auf dessen ID
   umgehaengt statt dem DB-FK ON DELETE SET NULL zu ueberlassen - ein
   SET NULL waere technisch unschaedlich, wuerde aber die Information
   "diese Submission/Mail lief ueber genau diesen Kontakt" stillschweigend
   verlieren. Geprueft wurden per SQLAlchemy-Modellsuche GENAU zwei harte
   FKs auf contact_persons.id (CandidateSubmission.contact_person_id,
   MailMessage.matched_contact_person_id, beide ON DELETE SET NULL) sowie
   eine weiche JSON-Referenz (MailingGroup.recipients, kind="contact") -
   gleiches Repoint-Muster wie merge_kanzlei_duplikate.py fuer
   ClientCompany. Wie dort: vor dem tatsaechlichen Loeschen wird live
   erneut gezaehlt, ob noch irgendeine Referenz auf die zu loeschende ID
   zeigt (count_contact_references innerhalb von apply_duplicate_deletions)
   - falls ja, wird NICHT geloescht.

Dry-run per Default, --commit schreibt tatsaechlich. Zusammenfassung am
Ende: was passiert ist, was uebersprungen wurde und warum.

Usage (von backend/, mit aktivierter venv):

    python scripts/fix_contact_data_quality_20260916.py            # dry run
    python scripts/fix_contact_data_quality_20260916.py --commit    # schreibt
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.contact_person import ContactPerson  # noqa: E402
from cc_crm.models.mail import MailMessage  # noqa: E402
from cc_crm.models.mailing_group import MailingGroup  # noqa: E402
from cc_crm.models.submission import CandidateSubmission  # noqa: E402

# --- Teil 1: Name-Split -----------------------------------------------------

# (id, first_name, last_name) - 71 Eintraege wie von Gegë per Live-API-Abzug
# geprueft und uebergeben. Einzelbuchstaben-Vornamen ("A", "T", ...) sind
# bewusst so - dort ist nur die Initiale aus der Mail-Adresse bekannt.
NAME_SPLITS: list[tuple[str, str, str]] = [
    ("42ad6718-cb84-4491-bfc4-f1a6e7aa17a9", "A", "Denk"),
    ("975b320c-b74d-4afd-af41-544cd81b1971", "A", "Frisch"),
    ("7f049a73-97ea-4c2e-84da-c6af6ecf4519", "A", "Meister"),
    ("1a4f4501-3d0d-4007-85a9-eaa65ddd14f1", "Andela", "Stamenkovic"),
    ("05f987d2-92a8-4986-9e8d-9e6426868be1", "Andreas", "Bietmann"),
    ("95221fb7-ed75-4e67-ad6a-a5ec557476d8", "Andre", "Kollmuss"),
    ("aba5eb51-8bdd-487e-b3aa-2da6f3363a9f", "A", "Niebuhr"),
    ("d3fea8a3-2285-4b1b-b39b-83bd5306b756", "Annette", "Gold"),
    ("dcf4bc4c-ef2d-43fd-8523-3b5855d82ea6", "B", "Engl"),
    ("dd250628-76ea-45c1-a040-a1719c4c4aa0", "Cathrin", "Ambacher"),
    ("7cc0eaec-973e-430f-ab14-f6602209aafd", "C", "Bode"),
    ("12930c02-ef2e-4300-a332-636cff6fc581", "C", "Gabriel"),
    ("1327d8bb-b3e8-46d3-879a-ded1ee02945a", "Claus", "Gossmann"),
    ("28cc71db-86a2-4255-88f5-7dd7500a9af3", "Corinna", "Prause"),
    ("ce4b5219-b7e1-4f6b-94a4-c14ad8905e00", "C", "Porten"),
    ("84225d90-8fb2-45ff-9601-c09d6561d643", "Daniel", "Waldraff"),
    ("e70adacf-7234-4a12-a6a9-dfb8dfcfcd4c", "Diana", "Brnjic"),
    ("726e9a13-053e-4e42-94b9-6177c52847c0", "D", "Schmeisser"),
    ("8674cf24-0a43-41d7-a878-019199056678", "D", "Vossen"),
    ("c2a14d5a-a658-4b34-ae12-b523bac6d248", "E", "Beyer"),
    ("029c7177-4239-4ed5-9baa-eaac0739b287", "E", "Vonrosenberg"),
    ("f17db72e-b688-4572-af35-95b1d092ec3f", "Freya", "Bockelmann"),
    ("21f951b0-0ca4-41ee-9c3c-8cf2c4ff0b60", "Hannes", "Stach"),
    ("6405ce2f-346e-44fe-bc65-9a74f96b97c6", "H", "Weyland"),
    ("ba73a6b6-351e-4249-a403-7edde9dc42a9", "I", "Classen"),
    ("692faa66-478c-407b-a6cd-8ef521019728", "Jan", "Kaup"),
    ("62008a75-158f-415d-beb3-fb7c7d32c283", "Jan", "Radloff"),
    ("d57a3ddf-74b5-44f0-ae00-b548721f13e7", "J", "Borowitz"),
    ("dbc6ee35-1afd-48b9-9a83-a2909a08e645", "Jelena", "Boehm"),
    ("cf69c613-3222-4729-bc61-b76aa918dc47", "J", "Gebelein"),
    ("031947ff-a2e9-45c5-87fd-a267b5f81244", "J", "Kess"),
    ("89d33b6d-810c-4e46-a0ca-67ed3a8fe911", "Joerdis", "Weithaler"),
    ("092168d4-cbab-4b09-b3eb-92df86141de7", "Jule", "Dillbahner"),
    ("de585d27-1d3f-4246-afdd-84a11ff57af8", "J", "Zeilhofer"),
    ("7ba68570-898d-44d5-97ca-f65f6bd1c53e", "Klaus", "Schneider"),
    ("139ad557-701b-4d29-8c81-9111b9d3ed16", "K", "Mueller"),
    ("efd87658-85c0-4dd8-b14d-59a21ae8e218", "L", "Lahser"),
    ("11261a8d-b77e-44df-a8ce-7d394efc7018", "Markus", "Reinhart"),
    ("4a99660e-39f0-4ad0-9466-2a23c70b8798", "Martin", "Kapfer"),
    ("97902f2b-5f53-4162-9656-ddad160c6097", "M", "Berges"),
    ("45f9e9e5-453b-4f40-9049-4d9c2b8e3a16", "Michaela", "Musial"),
    ("5afef2c5-e63a-4180-b143-7d63f731c26e", "Michael", "Baehrle"),
    ("48ee90c6-2e99-430e-a9b3-381c1a10b2e4", "Michael", "Bochenek"),
    ("ab25696e-3648-46d7-ba5f-2b870d6d81b6", "Michael", "Huber"),
    ("4816dcc3-3330-4ceb-8a31-83508db3f06c", "Michael", "Oberdorfer"),
    ("80737caf-0205-41de-8801-254ae933f59a", "M", "Mueller"),
    ("2b1c9e54-20d3-4bd1-8019-808643bc7b6e", "Monika", "Harpaintner"),
    ("b7df64c5-657f-4ff9-bd22-b7dc290aaf2b", "M", "Prokasky"),
    ("4082fb4a-6bf4-454f-8b27-b8d089314f8c", "M", "Quabeck"),
    ("fa5324dd-f45a-4d9f-b5c1-6e16745c6b07", "M", "Staykova"),
    ("fe2b684f-dbc4-4183-a0af-a8f3818e35ec", "N", "Gail"),
    ("a82b7e39-873b-4a0d-bf63-42ffb88ae3a4", "N", "Gutzwiller"),
    ("a6ea5157-b0d6-429b-b035-9a6d842b43d2", "N", "Mueller"),
    ("1fb57222-24cb-4dc3-8738-e5358fd0a2a0", "O", "Gebauer"),
    ("fa152c14-76b5-48b0-96d2-6ce1c43d809e", "Oliver", "Burchardt"),
    ("31739b40-caed-442b-8e9b-949d6581aac3", "O", "Schloeder"),
    ("963f0e89-89b4-473a-8c9f-4693bb5be751", "Robert", "Fahn"),
    ("06ee6417-a152-4543-88e8-986ad1e3c293", "Sabine", "Raith"),
    ("07e17dbc-c5d9-44b5-9317-a83e37469e4e", "Sandra", "Wiedemann"),
    ("c4d1aa87-6fb9-4812-b783-cae33276d872", "S", "Haerdter"),
    ("5dc54692-6032-43f1-a3a5-e4668c8c0207", "S", "Neppe"),
    ("0dad935b-7260-498a-bbe5-8cb3774476a7", "Sophia", "Wunderlich"),
    ("dec6112f-5039-4897-bac0-ff9aea925ca8", "S", "Schmitz"),
    ("50cac3ca-c248-43d8-8315-44904df8b69a", "S", "Sudhaus"),
    ("31ccedd2-abc9-4213-b4f6-324e7220fc36", "Stefanie", "Koelen"),
    ("4d42680d-492c-4ce2-8f0e-283f381d8179", "Stefan", "Sauer"),
    ("28e19318-8e26-4c75-be01-8bd06a3b533d", "T", "Maier"),
    ("aa851a46-adda-4134-b408-5d7cbf7a5d68", "T", "Mayer"),
    ("f352a355-5510-424f-868c-84bfd395bf56", "T", "Meyer"),
    ("e828dd2c-fdce-491f-87fd-087c526ba0a0", "U", "Feldkaemper"),
    ("2fc5ae16-6b15-4811-abca-c69d1c6f790a", "Y", "Panknin"),
    # Sonderfall: generisches mail@-Funktionspostfach (mail.nordheide@
    # kanzlei-bns.de), KEIN vorname.nachname-Muster - first_name bleibt
    # leer wie bei den anderen Funktionspostfaechern, nur last_name wird
    # bereinigt. Strukturell ein normaler NAME_SPLITS-Eintrag wie jeder
    # andere, deshalb hier statt in einer separaten Konstante.
    ("4ce31ff5-d3bf-49d8-8b65-59c13d2938b4", "", "Nordheide"),
]

# --- Teil 2: Dubletten -------------------------------------------------------

# (keep_id, delete_id, name_hint) - jeweils der vollstaendigere/aeltere
# Datensatz bleibt, der aermere/an einer Duplikat-Kanzlei haengende wird
# geloescht (siehe Modul-Docstring).
DUPLICATE_PAIRS: list[tuple[str, str, str]] = [
    (
        "f99edd88-cb73-47e5-8cf0-c33ad658a883",
        "b5fae401-1114-45d8-8312-82178d9ab5b9",
        "Waltraud Nolte",
    ),
    (
        "e19fb9ca-131c-4c46-8a97-8bb409339d9c",
        "19d33492-1b92-42e8-a972-d882aa639a01",
        "Elke Osenau",
    ),
    (
        "e8ee823b-4454-4ac3-9db7-4d966af7138e",
        "6cfdeea4-08e3-435a-8266-74b390e63ec5",
        "Jennifer Schallert",
    ),
]


def apply_name_splits(session: Session, *, apply: bool) -> tuple[int, int]:
    """Setzt first_name/last_name fuer alle NAME_SPLITS-Eintraege - live
    geprueft: ein Kontakt, der nicht mehr existiert oder dessen first_name
    bereits nicht mehr leer ist (z.B. zwischenzeitlich von jemandem
    bearbeitet), wird NICHT ueberschrieben, sondern als uebersprungen
    gemeldet."""
    fixed = 0
    skipped = 0
    for raw_id, first_name, last_name in NAME_SPLITS:
        contact = session.get(ContactPerson, uuid.UUID(raw_id))
        if contact is None:
            print(f"  UEBERSPRUNGEN {raw_id}: Kontakt existiert nicht (mehr).")
            skipped += 1
            continue
        if contact.first_name.strip():
            print(
                f"  UEBERSPRUNGEN {raw_id}: first_name ist bereits '{contact.first_name}' "
                f"(nicht mehr leer) - vermutlich zwischenzeitlich bearbeitet, nicht angefasst."
            )
            skipped += 1
            continue
        old_last_name = contact.last_name
        print(
            f"  {raw_id}: first_name='{first_name}', last_name='{old_last_name}' -> '{last_name}'"
        )
        if apply:
            contact.first_name = first_name
            contact.last_name = last_name
        fixed += 1
    return fixed, skipped


def count_contact_references(session: Session, contact_id: uuid.UUID) -> dict[str, int]:
    """Live-Zaehlung ALLER Referenzen auf einen ContactPerson-Datensatz -
    die zwei harten FKs (SET NULL) plus die weiche JSON-Referenz in
    MailingGroup.recipients. Wird sowohl fuer den Dry-Run-Bericht als auch
    als letzte Sicherung unmittelbar vor dem Loeschen genutzt."""
    counts = {
        "candidate_submissions": session.query(CandidateSubmission)
        .filter(CandidateSubmission.contact_person_id == contact_id)
        .count(),
        "mail_messages": session.query(MailMessage)
        .filter(MailMessage.matched_contact_person_id == contact_id)
        .count(),
    }
    mailing_hits = 0
    for group in session.query(MailingGroup).all():
        for recipient in group.recipients or []:
            if recipient.get("kind") == "contact" and str(recipient.get("id")) == str(contact_id):
                mailing_hits += 1
    counts["mailing_groups"] = mailing_hits
    return counts


def repoint_contact_references(
    session: Session, *, keep_id: uuid.UUID, delete_id: uuid.UUID, apply: bool
) -> dict[str, int]:
    """Haengt alle Referenzen auf delete_id auf keep_id um, BEVOR der
    Datensatz geloescht wird - siehe Modul-Docstring, warum das dem
    DB-seitigen ON DELETE SET NULL vorgezogen wird."""
    moved = {"candidate_submissions": 0, "mail_messages": 0, "mailing_groups": 0}

    submissions = (
        session.query(CandidateSubmission)
        .filter(CandidateSubmission.contact_person_id == delete_id)
        .all()
    )
    for submission in submissions:
        moved["candidate_submissions"] += 1
        if apply:
            submission.contact_person_id = keep_id

    messages = (
        session.query(MailMessage).filter(MailMessage.matched_contact_person_id == delete_id).all()
    )
    for message in messages:
        moved["mail_messages"] += 1
        if apply:
            message.matched_contact_person_id = keep_id

    keeper = session.get(ContactPerson, keep_id)
    for group in session.query(MailingGroup).all():
        recipients = group.recipients or []
        hit = False
        for recipient in recipients:
            if recipient.get("kind") == "contact" and str(recipient.get("id")) == str(delete_id):
                hit = True
                moved["mailing_groups"] += 1
                if apply:
                    recipient["id"] = str(keep_id)
                    if keeper is not None:
                        recipient["name"] = f"{keeper.first_name} {keeper.last_name}".strip()
                        recipient["email"] = keeper.email
        if hit and apply:
            group.recipients = recipients
            flag_modified(group, "recipients")

    return moved


def apply_duplicate_deletions(session: Session, *, apply: bool) -> tuple[int, int]:
    deleted = 0
    skipped = 0
    for keep_raw, delete_raw, name_hint in DUPLICATE_PAIRS:
        keep_id = uuid.UUID(keep_raw)
        delete_id = uuid.UUID(delete_raw)
        print(f"  Paar '{name_hint}': behalten={keep_id}, loeschen={delete_id}")

        keeper = session.get(ContactPerson, keep_id)
        loser = session.get(ContactPerson, delete_id)
        if keeper is None or loser is None:
            print("    UEBERSPRUNGEN: einer der beiden Datensaetze existiert nicht (mehr).")
            skipped += 1
            continue

        moved = repoint_contact_references(
            session, keep_id=keep_id, delete_id=delete_id, apply=apply
        )
        for label, count in moved.items():
            if count:
                print(f"    umgehaengt: {count}x {label}")
        # Die Nachpruefung "zeigt danach noch etwas auf delete_id" ist nur
        # im echten Lauf aussagekraeftig - im Dry-Run wurde ja bewusst NICHT
        # umgehaengt (siehe repoint_contact_references, apply=False), die
        # Zaehlung wuerde also immer "noch referenziert" melden, obwohl ein
        # echter --commit-Lauf das korrekt aufloesen wuerde.
        if apply:
            session.flush()
            remaining = count_contact_references(session, delete_id)
            still_referenced = {k: v for k, v in remaining.items() if v}
            if still_referenced:
                print(
                    f"    ABGEBROCHEN: nach dem Umhaengen zeigen noch Referenzen auf {delete_id}: "
                    f"{still_referenced} - NICHT geloescht."
                )
                skipped += 1
                continue

        print(f"    loesche ContactPerson {delete_id} ({loser.first_name} {loser.last_name})")
        if apply:
            session.delete(loser)
        deleted += 1
    return deleted, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit", action="store_true", help="Tatsaechlich schreiben (Default: nur anzeigen)."
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        print("=== Teil 1: Name-Split ===")
        fixed, split_skipped = apply_name_splits(session, apply=args.commit)

        print("\n=== Teil 2: Dubletten loeschen ===")
        deleted, dup_skipped = apply_duplicate_deletions(session, apply=args.commit)

        if args.commit:
            session.commit()
            print("\nCommitted.")
        else:
            session.rollback()
            print("\nDry run - nichts geschrieben. Mit --commit erneut ausfuehren.")

        total_contacts = session.query(ContactPerson).count()

    print("\n=== Zusammenfassung ===")
    print(f"Name-Split: {fixed} korrigiert, {split_skipped} uebersprungen")
    print(f"Dubletten:  {deleted} geloescht, {dup_skipped} uebersprungen")
    print(f"Kontakte gesamt (aktuell in der DB): {total_contacts}")


if __name__ == "__main__":
    main()
