"""Beschaffung eines gueltigen Microsoft-Graph-Access-Tokens fuer ein
`MailAccount` mit provider=microsoft_graph.

Der Access-Token selbst wird NIE persistiert (lebt nur ~60 Min., siehe
models/mail.py::MailAccount-Docstring) - jeder Aufruf tauscht das
gespeicherte, Fernet-verschluesselte Refresh-Token frisch gegen ein
Token-Paar. Microsoft rotiert das Refresh-Token bei JEDEM Aufruf
(offline_access) - das neue Refresh-Token wird deshalb sofort wieder
verschluesselt zurueckgeschrieben, sonst wuerde der naechste Aufruf mit dem
dann bereits ungueltigen alten Token scheitern.

Schlaegt der Refresh mit invalid_grant fehl (GraphReauthRequiredError),
wird `oauth_status` auf NEEDS_RECONNECT gesetzt und committed, BEVOR der
Fehler weitergereicht wird - Aufrufer (mail_sync.py, mail_send.py,
calendar_graph_sync.py) muessen dafuer keine eigene Fehlerbehandlung
bauen, der Zustand ist sofort in der Postfaecher-Oberflaeche sichtbar
("Postfach neu verbinden")."""

from __future__ import annotations

from sqlalchemy.orm import Session

from cc_crm.integrations.microsoft_graph.auth import GraphReauthRequiredError, refresh_access_token
from cc_crm.models.enums import MailAccountOAuthStatus
from cc_crm.models.mail import MailAccount
from cc_crm.services.mail_credentials import decrypt_password, encrypt_password


def get_valid_access_token(session: Session, account: MailAccount) -> str:
    if not account.encrypted_oauth_refresh_token:
        raise GraphReauthRequiredError(
            f"Postfach {account.address} hat kein gespeichertes Microsoft-Refresh-Token - "
            "bitte über 'Mit Microsoft anmelden' verbinden."
        )
    refresh_token = decrypt_password(account.encrypted_oauth_refresh_token)
    try:
        tokens = refresh_access_token(refresh_token=refresh_token)
    except GraphReauthRequiredError:
        account.oauth_status = MailAccountOAuthStatus.NEEDS_RECONNECT
        session.commit()
        raise

    account.encrypted_oauth_refresh_token = encrypt_password(tokens.refresh_token)
    account.oauth_scopes = tokens.scope
    account.oauth_status = MailAccountOAuthStatus.CONNECTED
    session.commit()
    return tokens.access_token
