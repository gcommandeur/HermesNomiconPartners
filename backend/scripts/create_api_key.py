"""Provision a long-lived API key for an agent/integration (Bullhorn sync,
future AI agents, webhooks, ...). The raw key is only ever shown once.

Usage (from backend/, with the venv active):

    python scripts/create_api_key.py "Bullhorn Sync"
    python scripts/create_api_key.py "Matching Agent"
    python scripts/create_api_key.py "Temporary Export Job" --expires-in-days 30
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.services.api_keys import ApiKeyService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="Name des Agents/der Integration")
    parser.add_argument(
        "--expires-in-days",
        type=int,
        default=None,
        help="Optional: Key laeuft nach dieser Anzahl Tage ab (Default: laeuft nie ab)",
    )
    args = parser.parse_args()

    expires_at = None
    if args.expires_in_days is not None:
        expires_at = datetime.now(UTC) + timedelta(days=args.expires_in_days)

    with SessionLocal() as session:
        api_key, raw_key = ApiKeyService(session).create(args.name, expires_at=expires_at)

    print(f"API-Key '{args.name}' angelegt (id={api_key.id}).")
    if expires_at is not None:
        print(f"Laeuft ab: {expires_at.isoformat()}")
    print(f"X-API-Key: {raw_key}")
    print("Dieser Wert wird nur einmal angezeigt - bitte sicher speichern.")


if __name__ == "__main__":
    main()
