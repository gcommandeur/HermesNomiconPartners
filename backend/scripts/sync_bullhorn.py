"""Pull Kandidaten/Kanzleien from Bullhorn into CC CRM.

Requires BULLHORN_CLIENT_ID, BULLHORN_CLIENT_SECRET, BULLHORN_USERNAME and
BULLHORN_PASSWORD (see docs/BULLHORN_LINKEDIN_IMPORT.md). Defaults to a dry
run that only prints what would happen - pass --commit to actually write.

Usage (from backend/, with the venv active):

    python scripts/sync_bullhorn.py candidates            # dry run, prints counts
    python scripts/sync_bullhorn.py candidates --commit    # actually imports
    python scripts/sync_bullhorn.py clients --commit --limit 500
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cc_crm.core.errors import ConflictError  # noqa: E402
from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.integrations.bullhorn import BullhornAuthError, BullhornClient  # noqa: E402
from cc_crm.schemas.candidate import CandidateCreate  # noqa: E402
from cc_crm.schemas.client_company import ClientCompanyCreate  # noqa: E402
from cc_crm.services.candidates import CandidateService  # noqa: E402
from cc_crm.services.clients import ClientCompanyService  # noqa: E402


def sync_candidates(*, limit: int, commit: bool) -> None:
    client = BullhornClient()
    records = client.fetch_candidates(count=limit)
    print(f"{len(records)} Kandidaten von Bullhorn abgerufen.")
    if not commit:
        for record in records[:5]:
            print(" preview:", client.normalize_candidate(record))
        print("Dry run - nichts geschrieben. Mit --commit erneut ausfuehren.")
        return

    imported = skipped = 0
    with SessionLocal() as session:
        service = CandidateService(session)
        for record in records:
            data = client.normalize_candidate(record)
            if not data.get("first_name") or not data.get("last_name"):
                skipped += 1
                continue
            try:
                service.create(CandidateCreate.model_validate(data))
                imported += 1
            except ConflictError:
                skipped += 1
    print(f"Importiert: {imported}, uebersprungen (Duplikat/unvollstaendig): {skipped}")


def sync_clients(*, limit: int, commit: bool) -> None:
    client = BullhornClient()
    records = client.fetch_client_corporations(count=limit)
    print(f"{len(records)} Kanzleien von Bullhorn abgerufen.")
    if not commit:
        for record in records[:5]:
            print(" preview:", client.normalize_client(record))
        print("Dry run - nichts geschrieben. Mit --commit erneut ausfuehren.")
        return

    imported = skipped = 0
    with SessionLocal() as session:
        service = ClientCompanyService(session)
        for record in records:
            data = client.normalize_client(record)
            if not data.get("name"):
                skipped += 1
                continue
            try:
                service.create(ClientCompanyCreate.model_validate(data))
                imported += 1
            except ConflictError:
                skipped += 1
    print(f"Importiert: {imported}, uebersprungen (Duplikat/unvollstaendig): {skipped}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bullhorn-Sync fuer CC CRM")
    parser.add_argument("entity", choices=["candidates", "clients"])
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--commit", action="store_true", help="Tatsaechlich schreiben statt Dry-Run"
    )
    args = parser.parse_args()

    try:
        if args.entity == "candidates":
            sync_candidates(limit=args.limit, commit=args.commit)
        else:
            sync_clients(limit=args.limit, commit=args.commit)
    except BullhornAuthError as error:
        print(f"Bullhorn-Fehler: {error}")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
