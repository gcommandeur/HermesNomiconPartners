"""Schreibt das OpenAPI-Schema der API in eine Datei (ohne laufenden Server und
unabhaengig davon, ob /openapi.json in Produktion abgeschaltet ist).

Aus dieser Datei erzeugt das Frontend seine API-Typen (`pnpm gen:api`). Die Datei ist
eingecheckt; `--check` (CI) schlaegt fehl, wenn sie nicht zum Code passt - dann hat
jemand die API geaendert, ohne die Typen zu erneuern.

Usage (von backend/, mit aktivierter venv):

    python scripts/export_openapi.py            # schreibt ../frontend/src/lib/api/openapi.json
    python scripts/export_openapi.py --check    # prueft nur
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
# Die App wird nur gebaut, nicht gestartet - kein DB-Zugriff noetig.
os.environ.setdefault("CC_CRM_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CC_CRM_LOG_LEVEL", "WARNING")
# Die API-Beschreibung enthaelt den Firmennamen aus den Einstellungen. Fest auf den Standard setzen,
# damit das Schema nicht von einer lokalen backend/.env abhaengt (die CI hat keine).
os.environ["CC_CRM_COMPANY_NAME"] = "Commandeur Consulting"

DEFAULT_TARGET = Path(__file__).resolve().parent.parent.parent / "frontend/src/lib/api/openapi.json"


def render() -> str:
    from cc_crm.main import create_app

    schema = create_app().openapi()
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--check", action="store_true", help="nur pruefen, nichts schreiben")
    args = parser.parse_args()

    expected = render()
    if args.check:
        current = args.target.read_text(encoding="utf-8") if args.target.exists() else ""
        if current != expected:
            print(
                f"{args.target} ist veraltet. Neu erzeugen mit:\n"
                "  cd backend && python scripts/export_openapi.py"
                " && cd ../frontend && pnpm gen:api",
                file=sys.stderr,
            )
            return 1
        print("OpenAPI-Schema ist aktuell.")
        return 0
    args.target.parent.mkdir(parents=True, exist_ok=True)
    args.target.write_text(expected, encoding="utf-8")
    print(f"Geschrieben: {args.target} ({len(expected.splitlines())} Zeilen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
