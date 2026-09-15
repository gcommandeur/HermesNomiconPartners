"""Zeitgesteuerter Mail- + Kalender-Sync fuer microsoft_graph-Postfaecher
(Auftrag "M365-Postfach-Integration").

Fuer IMAP/SMTP-Postfaecher aendert sich nichts - die bleiben unveraendert
manuell ueber "Sync auslösen" in Einstellungen -> Postfächer angestossen.
Dieses Skript ist der Einstiegspunkt fuer einen DigitalOcean-App-Platform-
"Scheduled Job" (siehe M365-Integrationsplan, Abschnitt 3): alle paar
Minuten per Cron aufgerufen, laeuft nur so lange wie der eigentliche Abruf
dauert (sekundengenaue Abrechnung, kein Dauer-Worker noetig).

Ein Fehler bei EINEM Postfach (z.B. abgelaufenes Refresh-Token) bricht den
Lauf fuer die uebrigen Postfaecher NICHT ab - gleiche Robustheit wie beim
manuellen Sync-Button.

Usage (von backend/, mit aktivierter venv):

    python scripts/run_graph_sync.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.enums import MailAccountOAuthStatus, MailAccountProvider  # noqa: E402
from cc_crm.models.mail import MailAccount  # noqa: E402
from cc_crm.services.calendar_graph_sync import sync_account_calendar  # noqa: E402
from cc_crm.services.mail_sync import sync_all_active  # noqa: E402


def main() -> None:
    with SessionLocal() as session:
        accounts = list(
            session.scalars(
                select(MailAccount).where(
                    MailAccount.provider == MailAccountProvider.MICROSOFT_GRAPH,
                    MailAccount.is_active.is_(True),
                    # Konten im Zustand "muss neu verbunden werden" werden
                    # uebersprungen statt bei jedem Lauf erneut zu
                    # scheitern - siehe MailAccountOAuthStatus-Docstring.
                    MailAccount.oauth_status != MailAccountOAuthStatus.NEEDS_RECONNECT,
                )
            )
        )
        if not accounts:
            print("Keine aktiven microsoft_graph-Postfächer zu synchronisieren.")
            return

        mail_results = sync_all_active(session, accounts=accounts)
        for result in mail_results:
            status = "ok" if result.ok else f"FEHLER: {result.error}"
            print(
                f"Mail-Sync {result.mail_account_id}: {status} "
                f"({result.fetched} abgerufen, {result.created_activities} Aktivitäten)"
            )

        for account in accounts:
            try:
                sync_account_calendar(session, account)
                print(f"Kalender-Sync {account.address}: ok")
            except Exception as exc:  # noqa: BLE001 - ein Postfach darf die anderen nicht blockieren
                print(f"Kalender-Sync {account.address}: FEHLER: {exc}")


if __name__ == "__main__":
    main()
