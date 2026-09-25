"""Zweiter, abschliessender Abgleichlauf nach der Entflechtung
(fix_client_company_false_merges_20260713.py): waehrend jener Lauf noch mit
einer Zwischenversion von services/name_matching.py arbeitete, wurde eine
weitere Regression entdeckt und behoben (siehe name_matching.py-Docstring):
generische Gattungsworte wie "Steuerberatung" wurden nur entfernt, wenn sie
durch ein Leerzeichen vom Eigennamen getrennt waren - "Faststeuerberatung"
(ohne Leerzeichen) wurde dadurch faelschlich NICHT mehr mit "Fast
Steuerberatung" (mit Leerzeichen, dieselbe Firma) zusammengefuehrt und ist
als eigene, unnoetige neue Kanzlei "Faststeuerberatung" gelandet. Ausserdem
war "Fast Steuerberatung"s eigenes website-Feld noch nie korrekt (haengt
seit dem urspruenglichen fehlerhaften Import auf "amp-steuerberatung.de").

Dieses Skript gleicht ALLE 116 urspruenglichen Kanzleien einmal vollstaendig
mit dem jetzt finalen, korrigierten Algorithmus ab:
1. Fuer jede der 1146 Domain-Zeilen wird bestimmt, zu welcher der 116
   urspruenglichen Kanzleien sie (falls ueberhaupt) gehoert.
2. Existiert fuer eine so zugeordnete Domain bereits eine eigene,
   eigenstaendige ClientCompany (aus dem urspruenglichen Import oder der
   ersten Entflechtung faelschlich als neu angelegt), wird diese wieder in
   die richtige urspruengliche Kanzlei zurueckgefuehrt: Kontakte werden
   verschoben, die ueberfluessige Kanzlei geloescht (falls keine Submissions/
   Mandate daran haengen - RESTRICT-FKs werden respektiert, im Zweifel wird
   NICHT geloescht und stattdessen gemeldet).
3. Fuer jede urspruengliche Kanzlei wird danach website (auf die
   bestpassende zugehoerige Domain) und email (aus allen tatsaechlich
   zugehoerigen Domains) neu berechnet.

Ausfuehren:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\fix_client_company_reconcile_v2_20260713.py
"""

from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

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
from cc_crm.models.job_mandate import JobMandate  # noqa: E402
from cc_crm.models.submission import CandidateSubmission  # noqa: E402
from cc_crm.services.name_matching import (  # noqa: E402
    SIMILARITY_THRESHOLD,
    name_similarity,
    normalize_company_name,
)

BASELINE_DB_PATH = Path(__file__).resolve().parents[2] / (
    "cc_crm_local_before_kanzlei_domain_import_20260713_221849.db"
)


def main() -> None:
    domain_rows = load_domain_rows()
    contact_rows = load_contact_rows()
    mailboxes = build_domain_mailboxes(contact_rows)
    persons = build_domain_persons(contact_rows)

    baseline_conn = sqlite3.connect(str(BASELINE_DB_PATH))
    baseline_names = [row[0] for row in baseline_conn.execute("select name from client_companies")]
    baseline_conn.close()
    normalized_baseline = [(name, normalize_company_name(name)) for name in baseline_names]

    # domain -> (baseline_name, score) fuer alle Domains, die zu einer der
    # 116 urspruenglichen Kanzleien gehoeren.
    correct_parent_of: dict[str, tuple[str, float]] = {}
    for row in domain_rows:
        domain = normalize_domain(row["Domain"])
        firma = row["Firma_vermutet"].strip()
        target = normalize_company_name(firma)
        best: tuple[str, float] | None = None
        for name, normalized in normalized_baseline:
            score = name_similarity(target, normalized)
            if score < SIMILARITY_THRESHOLD:
                continue
            if best is None or score > best[1]:
                best = (name, score)
        if best is not None:
            correct_parent_of[domain] = best

    correct_domains_by_parent: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for domain, (parent_name, score) in correct_parent_of.items():
        correct_domains_by_parent[parent_name].append((domain, score))

    baseline_names_set = set(baseline_names)

    session = SessionLocal()
    try:
        merged_back: list[tuple[str, str]] = []  # (domain/firma, richtiger_parent)
        blocked: list[tuple[str, str]] = []  # (name, grund)
        baseline_conflicts: list[tuple[str, str]] = []  # (name, richtiger_parent)

        for domain, (parent_name, _score) in correct_parent_of.items():
            standalone = session.query(ClientCompany).filter_by(website=f"https://{domain}").first()
            if standalone is None or standalone.name == parent_name:
                continue  # kein eigenstaendiger Datensatz, oder ist bereits der Parent selbst

            if standalone.name in baseline_names_set:
                # WICHTIG: standalone ist selbst eine der 116 urspruenglichen
                # Kanzleien (nicht ein faelschlich neu angelegter Datensatz) -
                # beide haben nur zufaellig dieselbe website, weil der
                # urspruenglich fehlerhafte Import ihr faelschlich dieselbe
                # Domain zugewiesen hat. NIEMALS eine echte, eigenstaendige
                # Kanzlei loeschen/deren Kontakte umhaengen - nur die falsche
                # website-Zuordnung entfernen (wird unten fuer den
                # tatsaechlichen Parent neu berechnet) und melden.
                standalone.website = None
                session.flush()
                baseline_conflicts.append((standalone.name, parent_name))
                continue

            parent = session.query(ClientCompany).filter_by(name=parent_name).first()
            if parent is None or parent.id == standalone.id:
                continue

            # RESTRICT-FKs respektieren - nicht loeschen, wenn Submissions/
            # Mandate an dieser (faelschlich eigenstaendigen) Kanzlei haengen.
            has_submissions = (
                session.query(CandidateSubmission)
                .filter_by(client_company_id=standalone.id)
                .first()
                is not None
            )
            has_mandates = (
                session.query(JobMandate).filter_by(client_company_id=standalone.id).first()
                is not None
            )
            if has_submissions or has_mandates:
                blocked.append((standalone.name, "hat Submissions/Mandate - nicht geloescht"))
                continue

            moved = session.query(ContactPerson).filter_by(client_company_id=standalone.id).all()
            for contact in moved:
                contact.client_company_id = parent.id
            session.flush()

            session.delete(standalone)
            session.flush()
            merged_back.append((domain, parent_name))

        session.commit()

        # website/email fuer jede betroffene urspruengliche Kanzlei neu
        # berechnen - website: die am besten passende zugehoerige Domain;
        # email: aus allen tatsaechlich zugehoerigen Domains kombiniert.
        recomputed: list[tuple[str, str | None, str | None, str | None, str | None]] = []
        affected_parent_names = {parent_name for _domain, parent_name in merged_back}
        affected_parent_names |= {parent_name for _name, parent_name in baseline_conflicts}
        affected_parent_names |= {name for name, _parent_name in baseline_conflicts}
        for parent_name in affected_parent_names:
            parent = session.query(ClientCompany).filter_by(name=parent_name).first()
            if parent is None:
                continue
            domains_here = sorted(
                correct_domains_by_parent.get(parent_name, []), key=lambda pair: -pair[1]
            )
            if not domains_here:
                continue

            best_domain = domains_here[0][0]
            old_website, old_email = parent.website, parent.email
            new_website = f"https://{best_domain}"

            combined_mailboxes = [email for d, _s in domains_here for email in mailboxes.get(d, [])]
            combined_persons = [p for d, _s in domains_here for p in persons.get(d, [])]
            new_email, _reason = pick_client_email(combined_mailboxes, combined_persons)

            parent.website = new_website
            parent.email = new_email
            session.flush()
            recomputed.append((parent_name, old_website, new_website, old_email, new_email))

        session.commit()
    finally:
        session.close()

    print("=== Zusammenfassung ===")
    print(f"Faelschlich eigenstaendige Kanzleien zurueckgefuehrt: {len(merged_back)}")
    for domain, parent_name in merged_back:
        print(f"  {domain:35} -> {parent_name!r}")
    if blocked:
        print(f"\nNicht geloescht (Submissions/Mandate vorhanden): {len(blocked)}")
        for name, reason in blocked:
            print(f"  {name!r}: {reason}")

    print(
        f"\nEchte Baseline-Kanzleien mit faelschlicher website-Kollision "
        f"(NICHT geloescht, nur website bereinigt): {len(baseline_conflicts)}"
    )
    for name, parent_name in baseline_conflicts:
        print(f"  {name!r} (kollidierte mit Domain von {parent_name!r})")

    print(f"\nUrspruengliche Kanzleien mit korrigierter Website/E-Mail: {len(recomputed)}")
    for name, old_w, new_w, old_e, new_e in recomputed:
        print(f"  {name!r}")
        print(f"    website: {old_w!r} -> {new_w!r}")
        print(f"    email:   {old_e!r} -> {new_e!r}")


if __name__ == "__main__":
    main()
