"""Provision a long-lived API key for an agent/integration (Bullhorn sync,
future AI agents, webhooks, ...). The raw key is only ever shown once.

Usage (from backend/, with the venv active):

    python scripts/create_api_key.py "Bullhorn Sync"
    python scripts/create_api_key.py "Matching Agent"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.services.api_keys import ApiKeyService  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    name = sys.argv[1]

    with SessionLocal() as session:
        api_key, raw_key = ApiKeyService(session).create(name)

    print(f"API-Key '{name}' angelegt (id={api_key.id}).")
    print(f"X-API-Key: {raw_key}")
    print("Dieser Wert wird nur einmal angezeigt - bitte sicher speichern.")


if __name__ == "__main__":
    main()
