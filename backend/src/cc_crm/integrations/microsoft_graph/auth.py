"""OAuth-Authorization-Code-Flow gegen Microsoft Entra ID (Delegated
Permissions) - reines HTTP, keine DB-/Session-Kenntnis. Aufrufer:
services/mail_oauth.py (Start/Callback) und services/graph_token_service.py
(Refresh vor jedem Sync-/Sende-/Kalender-Lauf).

Endpunkte liegen unter `login.microsoftonline.com/{tenant_id}/oauth2/v2.0/`
(v2-Endpoint, nicht der aeltere v1/ADAL-Endpoint) - siehe Microsoft-Graph-
Doku "Authorize access to web applications using OAuth 2.0 and Microsoft
Entra ID".
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from cc_crm.core.config import Settings, get_settings
from cc_crm.core.errors import BusinessRuleError

# Delegated Scopes fuer diese Integration - siehe M365-Integrationsplan
# (Entra-ID-App-Registrierung "HermesCRM Postfach-Integration"): offline_access
# fuer ein Refresh-Token, User.Read fuer die Basis-Anmeldung, der Rest fuer
# Mail-Versand/-Lesen und bidirektionalen Kalender-Sync. info@commandeur-
# consulting.de ist ein normales Benutzerpostfach (kein Shared Mailbox,
# bestaetigt) - deshalb ausschliesslich die eigenen (nicht ".Shared")
# Scope-Varianten.
GRAPH_SCOPES = "offline_access User.Read Mail.Send Mail.ReadWrite Calendars.ReadWrite"

# Schlanke Scopes NUR fuer "Mit Microsoft anmelden" am CRM-Login (eigener Flow,
# unabhaengig vom Postfach-Connect): Identitaet bestaetigen, kein Mail-/Kalender-
# Zugriff, kein offline_access (es wird kein Refresh-Token gespeichert).
LOGIN_SCOPES = "openid profile email User.Read"

_AUTHORITY = "https://login.microsoftonline.com"
_GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


class GraphAuthError(BusinessRuleError):
    """Autorisierungs-Code-Tausch oder Token-Refresh fehlgeschlagen."""


class GraphNotConfiguredError(GraphAuthError):
    """CC_CRM_MS_GRAPH_CLIENT_ID/_TENANT_ID/_CLIENT_SECRET fehlen - siehe
    core/config.py::Settings.ms_graph_*."""


@dataclass(frozen=True)
class GraphTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    scope: str


def _require_settings(settings: Settings | None = None) -> Settings:
    settings = settings or get_settings()
    if not (
        settings.ms_graph_client_id
        and settings.ms_graph_tenant_id
        and settings.ms_graph_client_secret
    ):
        raise GraphNotConfiguredError(
            "Microsoft-Graph-Integration ist nicht konfiguriert - "
            "CC_CRM_MS_GRAPH_CLIENT_ID/_TENANT_ID/_CLIENT_SECRET fehlen."
        )
    return settings


def build_authorization_url(
    *, redirect_uri: str, state: str, settings: Settings | None = None
) -> str:
    """Baut die URL, zu der der Browser fuer den Microsoft-Login/Consent
    weitergeleitet wird. `state` ist ein bereits signiertes, kurzlebiges
    Token (siehe integrations/microsoft_graph/oauth_state.py) - Microsoft
    reicht es unveraendert an die Redirect-URI zurueck."""
    settings = _require_settings(settings)
    params = {
        "client_id": settings.ms_graph_client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": GRAPH_SCOPES,
        "state": state,
    }
    return f"{_AUTHORITY}/{settings.ms_graph_tenant_id}/oauth2/v2.0/authorize?{urlencode(params)}"


def _token_request(
    data: dict[str, str], settings: Settings, *, require_refresh_token: bool = True
) -> GraphTokens:
    url = f"{_AUTHORITY}/{settings.ms_graph_tenant_id}/oauth2/v2.0/token"
    payload = {
        "client_id": settings.ms_graph_client_id,
        "client_secret": settings.ms_graph_client_secret,
        **data,
    }
    try:
        response = httpx.post(url, data=payload, timeout=20)
    except httpx.HTTPError as exc:
        raise GraphAuthError(f"Microsoft-Token-Endpoint nicht erreichbar: {exc}") from exc

    body = response.json() if response.content else {}
    if response.status_code != 200:
        description = body.get("error_description") or body.get("error") or response.text
        raise GraphAuthError(f"Microsoft-Token-Anfrage fehlgeschlagen: {description}")

    # offline_access liefert IMMER ein neues refresh_token zurueck (Rotation)
    # - fehlt es (sollte laut Doku nicht vorkommen), ist das ein klarer
    # Konfigurationsfehler (Scope nicht gewaehrt) und muss laut erkennbar
    # sein statt spaeter mit einem kryptischen invalid_grant beim naechsten
    # Refresh-Versuch.
    refresh_token: str = body.get("refresh_token") or ""
    if not refresh_token and require_refresh_token:
        raise GraphAuthError(
            "Microsoft hat kein refresh_token zurückgegeben - fehlt der "
            "'offline_access'-Scope im Consent?"
        )
    return GraphTokens(
        access_token=body["access_token"],
        refresh_token=refresh_token,
        expires_in=int(body.get("expires_in", 3600)),
        scope=body.get("scope", ""),
    )


def exchange_code_for_tokens(
    *, code: str, redirect_uri: str, settings: Settings | None = None
) -> GraphTokens:
    settings = _require_settings(settings)
    return _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": GRAPH_SCOPES,
        },
        settings,
    )


def build_login_authorization_url(
    *,
    redirect_uri: str,
    state: str,
    settings: Settings | None = None,
    scopes: str = LOGIN_SCOPES,
) -> str:
    """Autorisierungs-URL fuer den reinen Anmelde-Flow (LOGIN_SCOPES, eigene
    Redirect-URI) - bewusst getrennt von build_authorization_url oben."""
    settings = _require_settings(settings)
    params = {
        "client_id": settings.ms_graph_client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": scopes,
        "state": state,
        # Microsoft-Kontoauswahl immer zeigen: ohne das meldet ein im Browser
        # schon angemeldetes Microsoft-Konto ungefragt das "falsche" Konto an.
        "prompt": "select_account",
    }
    return f"{_AUTHORITY}/{settings.ms_graph_tenant_id}/oauth2/v2.0/authorize?{urlencode(params)}"


def exchange_code_for_login(
    *, code: str, redirect_uri: str, settings: Settings | None = None
) -> str:
    """Tauscht den Code des Anmelde-Flows; liefert nur das Access-Token (fuer
    `GET /me`), es wird nichts gespeichert."""
    settings = _require_settings(settings)
    tokens = _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": LOGIN_SCOPES,
        },
        settings,
        require_refresh_token=False,
    )
    return tokens.access_token


def exchange_code_for_login_tokens(
    *, code: str, redirect_uri: str, settings: Settings | None = None
) -> GraphTokens:
    """Wie exchange_code_for_login, aber fuer den Anmelde-Flow MIT Postfach-/
    Kalender-Rechten (GRAPH_SCOPES): liefert auch das Refresh-Token."""
    settings = _require_settings(settings)
    return _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": GRAPH_SCOPES,
        },
        settings,
    )


class GraphReauthRequiredError(GraphAuthError):
    """Refresh-Token wurde von Microsoft abgelehnt (invalid_grant) - das
    Postfach muss neu verbunden werden (siehe MailAccountOAuthStatus.
    NEEDS_RECONNECT), kein voruebergehender Fehler."""


def refresh_access_token(*, refresh_token: str, settings: Settings | None = None) -> GraphTokens:
    settings = _require_settings(settings)
    try:
        return _token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": GRAPH_SCOPES,
            },
            settings,
        )
    except GraphAuthError as exc:
        if "invalid_grant" in str(exc).lower():
            raise GraphReauthRequiredError(str(exc)) from exc
        raise


def fetch_own_profile(access_token: str) -> dict[str, str]:
    """`GET /me` - liefert u.a. mail/userPrincipalName/displayName, direkt
    nach dem Code-Tausch genutzt, um die tatsaechliche Postfachadresse zu
    ermitteln (nicht aus dem Frontend vertrauenswuerdig entgegennehmen)."""
    try:
        response = httpx.get(
            f"{_GRAPH_ROOT}/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise GraphAuthError(f"Microsoft Graph /me nicht erreichbar: {exc}") from exc
    if response.status_code != 200:
        raise GraphAuthError(f"Microsoft Graph /me fehlgeschlagen: {response.text}")
    profile: dict[str, str] = response.json()
    return profile
