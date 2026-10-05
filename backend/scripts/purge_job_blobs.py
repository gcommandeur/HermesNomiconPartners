"""Loescht liegen gebliebene Lebenslauf-Bytes aus der Job-Warteschlange (DSGVO).

Betrifft Jobs in `background_jobs`, die nicht mehr laufen werden (endgueltig fehlgeschlagen,
verwaist, erledigt mit Rest-Bytes) und aelter als N Tage sind. Siehe
services/job_queue.py::purge_stale_job_blobs. Frisch fehlgeschlagene Jobs verlieren ihre Bytes
schon beim Fehlschlag; dieses Skript raeumt Altbestand und abgestuerzte Worker auf.

STANDARD IST EIN PROBELAUF (zaehlt nur, aendert nichts). Gegen die Produktions-Datenbank nur
der Nutzer selbst und erst nach dem Probelauf:

    python scripts/purge_job_blobs.py                  # Probelauf
    python scripts/purge_job_blobs.py --apply          # wirklich loeschen
    python scripts/purge_job_blobs.py --apply --days 7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.services.job_queue import STALE_BLOB_DAYS, purge_stale_job_blobs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="wirklich loeschen (sonst Probelauf)")
    parser.add_argument("--days", type=int, default=STALE_BLOB_DAYS, help="Mindestalter in Tagen")
    args = parser.parse_args()
    with SessionLocal() as session:
        count = purge_stale_job_blobs(session, older_than_days=args.days, dry_run=not args.apply)
        if args.apply:
            print(f"{count} Job(s) bereinigt (Lebenslauf-Bytes und Dateinamen entfernt).")
        else:
            print(f"PROBELAUF: {count} Job(s) wuerden bereinigt. Mit --apply ausfuehren.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
