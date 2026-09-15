"""Orchestriert den "Mit Microsoft anmelden"-Flow (Auftrag "M365-Postfach-
Integration") - verbindet integrations/microsoft_graph/ (reines HTTP) mit
Session/DB.

Ablauf:
1. Frontend ruft `GET /mail-accounts/oauth/start` auf (normaler
   authentifizierter Aufruf ueber den Next.js-Proxy) -> `start_oauth_flow`
   baut die Microsoft-Autorisierungs-URL mit signiertem `state`
   (traegt current_user.id). Das Frontend leitet den Browser per
   `window.location.href` dorthin weiter (siehe frontend/src/lib/api/
   queries.ts::startMicrosoftOAuth).
2. Nutzer meldet sich bei Microsoft an/erteilt Consent, Microsoft leitet
   den Browser auf die Redirect-URI zurueck (direkt, OHNE CRM-Login-
   Cookie) -> `GET /mail-accounts/oauth/callback?code=...&state=...` ruft
   `handle_oauth_callback` auf: verifiziert `state`, tauscht den Code,
   legt/aktualisiert das MailAccount, gibt die Ziel-URL fuer den
   Redirect zurueck ins Frontend zurueck.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.integrations.microsoft_graph.auth import (
    build_authorization_url,
    exchange_code_for_tokens,
    fetch_own_profile,
)
from cc_crm.integrations.microsoft_graph.oauth_state import create_oauth_state, verify_oauth_state
from cc_crm.models.enums import MailAccountOAuthStatus, MailAccountProvider
from cc_crm.models.mail import MailAccount
from cc_crm.services.mail_credentials import encrypt_password


def start_oauth_flow(*, redirect_uri: str, current_user_id: uuid.UUID) -> str:
    state = create_oauth_state(current_user_id)
    return build_authorization_url(redirect_uri=redirect_uri, state=state)


def handle_oauth_callback(
    session: Session, *, code: str, state: str, redirect_uri: str
) -> MailAccount:
    """Tauscht den Code, ermittelt die tatsaechliche Postfachadresse ueber
    `GET /me` (bewusst NICHT aus dem Frontend/Query-Parameter uebernommen -
    die Adresse muss von Microsoft selbst bestaetigt sein) und legt das
    MailAccount an bzw. wandelt ein bestehendes IMAP-Konto derselben
    Adresse in place um (siehe M365-Integrationsplan, Migrationspfad)."""
    user_id = verify_oauth_state(state)
    tokens = exchange_code_for_tokens(code=code, redirect_uri=redirect_uri)
    profile = fetch_own_profile(tokens.access_token)
    address = (profile.get("mail") or profile.get("userPrincipalName") or "").strip().lower()
    if not address:
        from cc_crm.integrations.microsoft_graph.auth import GraphAuthError

        raise GraphAuthError("Microsoft Graph /me hat keine E-Mail-Adresse geliefert.")
    display_name = profile.get("displayName") or address

    account = session.scalar(select(MailAccount).where(MailAccount.address == address))
    if account is None:
        account = MailAccount(
            address=address,
            label=display_name[:80],
            provider=MailAccountProvider.MICROSOFT_GRAPH,
        )
        session.add(account)
    else:
        # Bestehendes IMAP-Konto derselben Adresse wird in place umgewandelt
        # statt eine zweite Zeile anzulegen - erhaelt id und damit alle
        # bereits verknuepften MailMessage/Activity-Datensaetze (siehe
        # M365-Integrationsplan, Abschnitt Migrationspfad).
        account.provider = MailAccountProvider.MICROSOFT_GRAPH
        account.imap_host = None
        account.smtp_host = None
        account.username = None
        account.encrypted_password = None
        account.last_seen_uid = None
        account.sync_error = None

    account.encrypted_oauth_refresh_token = encrypt_password(tokens.refresh_token)
    account.oauth_scopes = tokens.scope
    account.oauth_status = MailAccountOAuthStatus.CONNECTED
    account.oauth_connected_by_user_id = user_id
    account.is_active = True
    session.commit()
    session.refresh(account)
    return account
