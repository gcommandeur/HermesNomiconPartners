"""Anmeldung am CRM ueber Microsoft Entra ID ("Mit Microsoft anmelden").

Eigener Flow, unabhaengig vom Postfach-Connect (services/mail_oauth.py): andere
Scopes, andere Redirect-URI, anderer Zweck. Microsoft bestaetigt die Identitaet
im eigenen Firmen-Tenant (CC_CRM_MS_GRAPH_TENANT_ID - Konten anderer Tenants
koennen den Flow gar nicht abschliessen); danach wird ein BESTEHENDER, aktiver
CRM-Nutzer mit derselben E-Mail-Adresse angemeldet. Nutzer werden NIE
automatisch angelegt (Governance-Entscheidung)."""

from __future__ import annotations

import hmac
import logging
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.config import get_settings
from cc_crm.core.errors import AuthenticationError
from cc_crm.integrations.microsoft_graph.auth import (
    GRAPH_SCOPES,
    LOGIN_SCOPES,
    GraphAuthError,
    GraphTokens,
    build_login_authorization_url,
    exchange_code_for_login,
    exchange_code_for_login_tokens,
    fetch_own_profile,
    require_single_tenant_for_login,
)
from cc_crm.integrations.microsoft_graph.oauth_state import (
    InvalidOAuthStateError,
    create_login_state,
    verify_login_state,
)
from cc_crm.models.enums import MailAccountOAuthStatus
from cc_crm.models.mail import MailAccount
from cc_crm.models.user import User
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.services.auth import AuthService
from cc_crm.services.mail_oauth import store_connection

logger = logging.getLogger("cc_crm.microsoft_login")

NO_ACCOUNT_MESSAGE = (
    "Kein Konto für diese E-Mail-Adresse - bitte einen Admin bitten, dich anzulegen."
)


def start_login(*, redirect_uri: str) -> tuple[str, str]:
    """(Autorisierungs-URL, nonce). Die nonce muss der Aufrufer als httpOnly-
    Cookie im Browser ablegen; im Callback wird sie gegen den State geprueft."""
    require_single_tenant_for_login()
    nonce = secrets.token_urlsafe(32)
    scopes = GRAPH_SCOPES if get_settings().ms_login_connects_mailbox else LOGIN_SCOPES
    url = build_login_authorization_url(
        redirect_uri=redirect_uri, state=create_login_state(nonce), scopes=scopes
    )
    return url, nonce


def complete_login(
    session: Session, *, code: str, state: str, cookie_nonce: str | None, redirect_uri: str
) -> tuple[User, str]:
    """Prueft State + Browser-Bindung, tauscht den Code, ermittelt die von
    Microsoft bestaetigte Adresse und stellt die Session aus. Liefert
    (Nutzer, Session-Token)."""
    require_single_tenant_for_login()
    state_nonce = verify_login_state(state)
    if not cookie_nonce or not hmac.compare_digest(state_nonce, cookie_nonce):
        raise InvalidOAuthStateError(
            "Die Anmeldung wurde in einem anderen Browser gestartet - bitte erneut starten."
        )
    connect_mailbox = get_settings().ms_login_connects_mailbox
    if connect_mailbox:
        tokens = exchange_code_for_login_tokens(code=code, redirect_uri=redirect_uri)
        access_token = tokens.access_token
    else:
        tokens = None
        access_token = exchange_code_for_login(code=code, redirect_uri=redirect_uri)
    profile = fetch_own_profile(access_token)
    # Gaeste (B2B-Einladung) im Firmen-Tenant duerfen sich nie anmelden: ihre `mail` ist die
    # externe Adresse und koennte zufaellig zu einem Hermes-Konto passen.
    if str(profile.get("userType") or "").strip().lower() == "guest":
        raise AuthenticationError(NO_ACCOUNT_MESSAGE)
    oid = str(profile.get("id") or "").strip().lower()
    if not oid:
        raise GraphAuthError("Microsoft hat keine Kennung (id) geliefert.")
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
    _check_or_bind_oid(session, user, oid)
    if tokens is not None:
        _connect_mailbox(session, user, tokens, profile)
    return user, AuthService(session).issue_session(user)


def _audit(session: Session, user: User, action: str, values: dict[str, str]) -> None:
    AuditLogRepository(session).create(
        {
            "entity_type": "user",
            "entity_id": user.id,
            "action": action,
            "changed_by": user.email,
            "new_values": values,
        }
    )


def _check_or_bind_oid(session: Session, user: User, oid: str) -> None:
    """Trust-on-first-use: beim ersten Login wird die Microsoft-Kennung gebunden
    (Zuordnung dabei ueber die E-Mail), danach muss sie uebereinstimmen. Jede
    Abweichung wird abgelehnt - mit derselben neutralen Meldung wie "kein Konto" -
    und im Audit-Log festgehalten (nur die letzten Zeichen der Kennung)."""
    if user.ms_oid is not None:
        if not hmac.compare_digest(user.ms_oid, oid):
            _audit(
                session,
                user,
                "microsoft_login_oid_mismatch",
                {"gebunden_endet_auf": user.ms_oid[-6:], "angemeldet_endet_auf": oid[-6:]},
            )
            session.commit()
            logger.warning("Microsoft-Login abgelehnt: Kennung weicht ab (Nutzer %s)", user.id)
            raise AuthenticationError(NO_ACCOUNT_MESSAGE)
        return
    taken = session.scalar(select(User.id).where(User.ms_oid == oid, User.id != user.id))
    if taken is not None:
        _audit(session, user, "microsoft_login_oid_conflict", {"angemeldet_endet_auf": oid[-6:]})
        session.commit()
        logger.warning("Microsoft-Login abgelehnt: Kennung gehoert zu einem anderen Nutzer")
        raise AuthenticationError(NO_ACCOUNT_MESSAGE)
    user.ms_oid = oid
    _audit(session, user, "microsoft_oid_bound", {"endet_auf": oid[-6:]})
    session.commit()


def _connect_mailbox(
    session: Session, user: User, tokens: GraphTokens, profile: dict[str, Any]
) -> None:
    """Postfach/Kalender des Anmeldenden verbinden. Darf die Anmeldung NIE
    verhindern (Fehler werden nur geloggt) und ueberschreibt kein Postfach, das
    ein ANDERER Nutzer verbunden hat."""
    try:
        address = (profile.get("mail") or profile.get("userPrincipalName") or "").strip().lower()
        existing = session.scalar(select(MailAccount).where(MailAccount.address == address))
        if (
            existing is not None
            and existing.oauth_connected_by_user_id not in (None, user.id)
            and existing.oauth_status == MailAccountOAuthStatus.CONNECTED
        ):
            logger.warning("Postfach %s gehoert einem anderen Nutzer - nicht verbunden.", address)
            return
        store_connection(session, user.id, tokens, profile)
    except Exception:  # noqa: BLE001 - die Anmeldung selbst ist wichtiger
        session.rollback()
        logger.exception("Postfach-Verbindung beim Microsoft-Login fehlgeschlagen")
