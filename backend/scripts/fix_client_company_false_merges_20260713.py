"""Einmalige Entflechtung fuer den urspruenglichen Kanzlei-Domain-Import
(import_kanzlei_domains_20260713.py): das damals verwendete Fuzzy-Namens-
Matching hatte einen Bug (siehe services/name_matching.py-Docstring, Fix
2026-07-13) - generische Gattungsworte wie "Steuerberatung"/"Kollegen"/
"Treuhand" wurden nicht aus dem Vergleich entfernt und eine zu grosszuegige
Substring-Sonderregel liess kurze Abkuerzungen wie "bb" als Treffer in
"Stübben" durchgehen. Ergebnis: 87 Domain-Zeilen (26 bestehende Kanzleien
betroffen, Extremfall "Fast Steuerberatung" mit 29 fremden Firmen) wurden
faelschlich mit einer bestehenden Kanzlei zusammengefuehrt statt eine eigene
neue Kanzlei zu werden.

Vorgehen:
1. Fuer jede Domain-Zeile wird rekonstruiert, was der URSPRUENGLICHE (fehler-
   hafte) Algorithmus entschieden hat (alte Logik hier absichtlich als
   Kopie belassen, NICHT services/name_matching.py - das enthaelt jetzt die
   korrigierte Version) und was der KORRIGIERTE Algorithmus (aktuelle
   services/name_matching.py) entscheiden wuerde - beides nur gegen die
   116 urspruenglichen Kanzleien (Stand vor dem Kanzlei-Domain-Import,
   siehe BASELINE_DB_PATH).
2. Domains, die unter dem korrigierten Algorithmus GAR NICHT mehr matchen,
   werden als eigene neue ClientCompany (status=PROSPECT) angelegt; ihre
   zuvor faelschlich der falschen Kanzlei zugeordneten Kontakte (erkannt an
   der E-Mail-Domain) werden dorthin verschoben; die E-Mail der neuen
   Kanzlei wird aus ihren eigenen Daten neu berechnet.
3. Domains, die unter dem korrigierten Algorithmus einer ANDEREN bestehenden
   Kanzlei zugeordnet wuerden als urspruenglich (statt gar keiner) werden
   NICHT automatisch verschoben, sondern nur zur manuellen Pruefung
   ausgegeben - das waere eine inhaltliche Ermessensentscheidung.
4. Domains, die weiterhin (unter altem UND neuem Algorithmus) derselben
   Kanzlei zugeordnet werden, bleiben unveraendert (z.B. echte Filialnetze
   wie Ecovis/PwC/Afileon/ETL - siehe Aufgabenstellung, das ist explizit
   gewuenschtes Verhalten, keine Dublette).
5. Fuer jede betroffene urspruengliche Kanzlei wird die E-Mail danach neu aus
   den tatsaechlich noch zugehoerigen Domains berechnet (pick_client_email).

Ausfuehren:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\fix_client_company_false_merges_20260713.py
"""

from __future__ import annotations

import re
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Callable
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from import_kanzlei_domains_20260713 import (  # noqa: E402
    build_domain_mailboxes,
    build_domain_persons,
    load_contact_rows,
    load_domain_rows,
    normalize_domain,
    pick_client_email,
)

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.contact_person import ContactPerson  # noqa: E402
from cc_crm.models.enums import ClientStatus  # noqa: E402
from cc_crm.schemas.client_company import ClientCompanyCreate  # noqa: E402
from cc_crm.services.clients import ClientCompanyService  # noqa: E402
from cc_crm.services.name_matching import (  # noqa: E402
    SIMILARITY_THRESHOLD,
    name_similarity,
    normalize_company_name,
)

BASELINE_DB_PATH = Path(__file__).resolve().parents[1] / (
    "cc_crm_local_before_kanzlei_domain_import_20260713_221849.db"
)

# --- Rekonstruktion der URSPRUENGLICHEN (fehlerhaften) Matching-Logik, wie
# sie vor dem Fix in services/name_matching.py stand - AUSSCHLIESSLICH fuer
# die forensische Feststellung "was hat der erste Lauf entschieden", nicht
# fuer neue Entscheidungen verwenden.
_OLD_LEGAL_SUFFIX_RE = re.compile(
    r"\b("
    r"gmbh\s*&\s*co\.?\s*kg|gmbh|mbh|mbb|ag|kgaa|kg|ohg|gbr|e\.?\s*k\.?|e\.?\s*v\.?|"
    r"partg\s*mbb|partgmbb|partg|partnerschaftsgesellschaft(\s*mbb)?|"
    r"steuerberatungsgesellschaft|wirtschaftsprüfungsgesellschaft|"
    r"rechtsanwaltsgesellschaft|treuhandgesellschaft|"
    r"steuerberater(in)?|wirtschaftsprüfer(in)?|rechtsanwälte|rechtsanwalt|"
    r"und\s+partner|&\s*partner|partner"
    r")\b",
    re.IGNORECASE,
)
_OLD_PUNCT_RE = re.compile(r"[.,&/\-]")
_OLD_WS_RE = re.compile(r"\s+")
_OLD_THRESHOLD = 0.72


def _old_normalize(name: str) -> str:
    value = _OLD_LEGAL_SUFFIX_RE.sub(" ", name)
    value = _OLD_PUNCT_RE.sub(" ", value)
    return _OLD_WS_RE.sub(" ", value).strip().casefold()


def _old_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


def _best_match(
    target_raw: str,
    candidates: list[tuple[str, str]],
    normalize_fn: Callable[[str], str],
    similarity_fn: Callable[[str, str], float],
    threshold: float,
) -> tuple[str, float] | None:
    target = normalize_fn(target_raw)
    best: tuple[str, float] | None = None
    for name, normalized in candidates:
        score = similarity_fn(target, normalized)
        if score < threshold:
            continue
        if best is None or score > best[1]:
            best = (name, score)
    return best


def main() -> None:
    domain_rows = load_domain_rows()
    contact_rows = load_contact_rows()
    mailboxes = build_domain_mailboxes(contact_rows)
    persons = build_domain_persons(contact_rows)

    baseline_conn = sqlite3.connect(str(BASELINE_DB_PATH))
    baseline_names = [row[0] for row in baseline_conn.execute("select name from client_companies")]
    baseline_conn.close()
    print(f"Baseline-Kanzleien (vor dem Kanzlei-Domain-Import): {len(baseline_names)}")

    old_candidates = [(name, _old_normalize(name)) for name in baseline_names]
    new_candidates = [(name, normalize_company_name(name)) for name in baseline_names]

    to_split: list[tuple[str, str, str]] = []  # (domain, firma, alter_falscher_parent)
    flagged_diff: list[tuple[str, str, str, str]] = []  # (domain, firma, alt, neu)
    remaining_domains_by_parent: dict[str, list[str]] = defaultdict(list)

    for row in domain_rows:
        domain = normalize_domain(row["Domain"])
        firma = row["Firma_vermutet"].strip()

        old_best = _best_match(
            firma, old_candidates, _old_normalize, _old_similarity, _OLD_THRESHOLD
        )
        if old_best is None:
            continue  # war schon urspruenglich eine eigene neue Kanzlei

        new_best = _best_match(
            firma, new_candidates, normalize_company_name, name_similarity, SIMILARITY_THRESHOLD
        )

        if new_best is not None and new_best[0] == old_best[0]:
            remaining_domains_by_parent[old_best[0]].append(domain)
            continue

        if new_best is not None:
            flagged_diff.append((domain, firma, old_best[0], new_best[0]))
            continue

        to_split.append((domain, firma, old_best[0]))

    print(f"Zu entflechtende Domains (werden eigene neue Kanzlei): {len(to_split)}")
    print(
        f"Abweichend gematcht, NICHT automatisch verschoben (manuell pruefen): {len(flagged_diff)}"
    )
    for domain, firma, alt, neu in flagged_diff:
        print(f"  {domain} ({firma!r}): alt={alt!r} -> neu={neu!r}")

    session = SessionLocal()
    try:
        client_service = ClientCompanyService(session)
        split_examples: list[
            tuple[str, str, int]
        ] = []  # (domain, neuer_name, verschobene_kontakte)
        affected_parents: set[str] = set()

        for domain, firma, wrong_parent_name in to_split:
            parent = session.query(ClientCompany).filter_by(name=wrong_parent_name).first()
            if parent is None:
                print(
                    f"  WARNUNG: urspruengliche Kanzlei {wrong_parent_name!r} nicht mehr gefunden."
                )
                continue
            affected_parents.add(wrong_parent_name)

            # Idempotenz + doppelte Firma_vermutet-Werte (z.B. "Kuepper
            # Kollegen" taucht fuer zwei Domains -.com und -.de- auf, echte
            # gleiche Marke, zwei TLDs - wie Afileon.com/.co im
            # urspruenglichen Import): zuerst pruefen, ob fuer diese Domain
            # oder denselben Namen schon eine entflochtene Kanzlei existiert
            # (aus einem frueheren/abgebrochenen Lauf oder einer vorherigen
            # Zeile in diesem Lauf), statt gegen den UNIQUE-Constraint auf
            # name zu laufen.
            target_website = f"https://{domain}"
            new_company = session.query(ClientCompany).filter_by(website=target_website).first()
            if new_company is None:
                new_company = session.query(ClientCompany).filter_by(name=firma).first()

            moved_contacts = (
                session.query(ContactPerson)
                .filter(ContactPerson.client_company_id == parent.id)
                .filter(ContactPerson.email.ilike(f"%@{domain}"))
                .all()
            )

            if new_company is None:
                new_company = client_service.create(
                    ClientCompanyCreate(
                        name=firma, website=target_website, status=ClientStatus.PROSPECT
                    )
                )
            elif not new_company.website:
                new_company.website = target_website
                session.flush()

            for contact in moved_contacts:
                contact.client_company_id = new_company.id
            session.flush()

            if not new_company.email:
                new_email, _reason = pick_client_email(
                    mailboxes.get(domain, []), persons.get(domain, [])
                )
                if new_email:
                    new_company.email = new_email
                session.flush()

            split_examples.append((domain, new_company.name, len(moved_contacts)))

        session.commit()

        # E-Mail der urspruenglichen (jetzt bereinigten) Kanzleien neu
        # berechnen - nur aus den Domains, die tatsaechlich noch zu ihnen
        # gehoeren (remaining_domains_by_parent).
        recomputed_parents: list[tuple[str, str | None, str | None]] = []
        for parent_name in affected_parents:
            parent = session.query(ClientCompany).filter_by(name=parent_name).first()
            if parent is None:
                continue
            remaining = remaining_domains_by_parent.get(parent_name, [])
            combined_mailboxes = [email for d in remaining for email in mailboxes.get(d, [])]
            combined_persons = [p for d in remaining for p in persons.get(d, [])]
            new_email, _reason = pick_client_email(combined_mailboxes, combined_persons)
            old_email = parent.email
            if new_email != old_email:
                parent.email = new_email
                session.flush()
            recomputed_parents.append((parent_name, old_email, new_email))

        session.commit()
    finally:
        session.close()

    print("\n=== Zusammenfassung ===")
    print(f"Neue, entflochtene Kanzleien angelegt: {len(split_examples)}")
    print(f"Betroffene urspruengliche Kanzleien (Kontakte verschoben): {len(affected_parents)}")
    total_moved_contacts = sum(count for *_, count in split_examples)
    print(f"Verschobene Kontakte insgesamt: {total_moved_contacts}")

    print("\nStichprobe entflochtener Kanzleien (Domain, neuer Name, verschobene Kontakte):")
    for domain, name, count in split_examples[:10]:
        print(f"  {domain:35} {name!r:45} {count} Kontakte")

    print("\nE-Mail-Neuberechnung der urspruenglichen Kanzleien (Name, alt, neu):")
    for name, old_email, new_email in recomputed_parents:
        marker = " (geaendert)" if old_email != new_email else ""
        print(f"  {name!r:60} {old_email!r} -> {new_email!r}{marker}")


if __name__ == "__main__":
    main()
