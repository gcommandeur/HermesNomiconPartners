"""Dauerlaufender Worker fuer die Job-Warteschlange (services/job_queue.py).

Nur noetig, wenn der Webprozess die Jobs NICHT selbst abarbeitet
(CC_CRM_EMBEDDED_WORKER=false). Mehrere Worker gleichzeitig sind erlaubt
(Postgres: FOR UPDATE SKIP LOCKED).

Usage (von backend/):  python scripts/run_worker.py
"""

from __future__ import annotations

import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cc_crm.core.config import get_settings  # noqa: E402
from cc_crm.core.observability import configure_logging  # noqa: E402
from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.services.job_queue import run_worker_loop  # noqa: E402


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.json_logs)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    run_worker_loop(SessionLocal, stop)


if __name__ == "__main__":
    main()
