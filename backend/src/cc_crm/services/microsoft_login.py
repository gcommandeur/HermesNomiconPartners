"""Anmeldung am CRM ueber Microsoft Entra ID ("Mit Microsoft anmelden").

Eigener Flow, unabhaengig vom Postfach-Connect (services/mail_oauth.py): andere
Scopes, andere Redirect-URI, anderer Zweck. Microsoft bestaetigt die Identitaet
im eigenen Firmen-Tenant (CC_CRM_MS_GRAPH_TENANT_ID - Konten anderer Tenants
koennen den Flow gar nicht abschliessen); danach wird ein BESTEHENDER, aktiver
CRM-Nutzer mit derselben E-Mail-Adresse angemeldet. Nutzer werden NIE
automatisch angelegt (Governance-Entscheidung)."""

from __future__ import annotations

import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import AuthenticationError
from cc_crm.integrations.microsoft_graph.auth import (
    GraphAuthError,
    build_login_authorization_url,
    exchange_code_for_login,
    fetch_own_profile,
)
from cc_crm.integrations.microsoft_graph.oauth_state import (
    InvalidOAuthStateError,
    create_login_state,
    verify_login_state,
)
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService

NO_ACCOUNT_MESSAGE = (
    "Kein Konto für diese E-Mail-Adresse - bitte einen Admin bitten, dich anzulegen."
)


def start_login(*, redirect_uri: str) -> tuple[str, str]:
    """(Autorisierungs-URL, nonce). Die nonce muss der Aufrufer als httpOnly-
    Cookie im Browser ablegen; im Callback wird sie gegen den State geprueft."""
    nonce = secrets.token_urlsafe(32)
    url = build_login_authorization_url(
        redirect_uri=redirect_uri, state=create_login_state(nonce)
    )
    return url, nonce


def complete_login(
    session: Session, *, code: str, state: str, cookie_nonce: str | None, redirect_uri: str
) -> tuple[User, str]:
    """Prueft State + Browser-Bindung, tauscht den Code, ermittelt die von
    Microsoft bestaetigte Adresse und stellt die Session aus. Liefert
    (Nutzer, Session-Token)."""
    state_nonce = verify_login_state(state)
    if not cookie_nonce or not hmac.compare_digest(state_nonce, cookie_nonce):
        raise InvalidOAuthStateError(
            "Die Anmeldung wurde in einem anderen Browser gestartet - bitte erneut starten."
        )
    access_token = exchange_code_for_login(code=code, redirect_uri=redirect_uri)
    profile = fetch_own_profile(access_token)
    candidates = []
    for key in ("mail", "userPrincipalName"):
        value = (profile.get(key) or "").strip().lower()
        if value and value not in candidates:
            candidates.append(value)
    if not candidates:
        raise GraphAuthError("Microsoft hat keine E-Mail-Adresse geliefert.")
    # Inaktive Nutzer werden wie nicht vorhandene behandelt (gleiche Meldung):
    # wie beim Passwort-Login (AuthService._verify_credentials) verraet die
    # Antwort nicht, ob das Konto existiert, aber deaktiviert ist.
    user = session.scalar(
        select(User).where(User.email.in_(candidates), User.is_active.is_(True)).limit(1)
    )
    if user is None:
        raise AuthenticationError(NO_ACCOUNT_MESSAGE)
    return user, AuthService(session).issue_session(user)
