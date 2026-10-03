"""Endpunkte fuer "Mit Microsoft anmelden" (siehe services/microsoft_login.py).

Beide Routen sind OEFFENTLICH (kein Bearer-Token): der Browser ist noch nicht
angemeldet, und Microsoft springt den Callback direkt an - analog zu
mail_accounts.public_router. Abgesichert wird ueber den signierten State plus
die Browser-gebundene nonce (Cookie). Frontend und Backend teilen sich die
Domain (App-Platform-Routing /api/v1), das Backend setzt deshalb den
Session-Cookie selbst und leitet zurueck ins Frontend - kein Token in der URL."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.core.config import get_settings
from cc_crm.core.errors import AuthenticationError, BusinessRuleError
from cc_crm.core.rate_limit import client_ip, login_rate_limiter
from cc_crm.services.auth import SESSION_LIFETIME
from cc_crm.services.microsoft_login import complete_login, start_login

logger = logging.getLogger("cc_crm.microsoft_login")

public_router = APIRouter(prefix="/auth/microsoft")

NONCE_COOKIE = "cc_crm_ms_login"


def _frontend_origin() -> str:
    settings = get_settings()
    return str(settings.cors_origins[0]).rstrip("/") if settings.cors_origins else ""


def _redirect_uri() -> str:
    """Muss Zeichen fuer Zeichen mit der in Entra ID hinterlegten Redirect-URI
    uebereinstimmen (siehe docs/DEPLOYMENT.md)."""
    return f"{_frontend_origin()}{get_settings().api_prefix}/auth/microsoft/callback"


def _cookie_path() -> str:
    return f"{get_settings().api_prefix}/auth/microsoft"


def _is_https() -> bool:
    return _frontend_origin().startswith("https://")


def _login_error(message: str) -> RedirectResponse:
    from urllib.parse import quote

    response = RedirectResponse(f"{_frontend_origin()}/login?error={quote(message[:200])}")
    response.delete_cookie(NONCE_COOKIE, path=_cookie_path())
    return response


@public_router.get("/login", include_in_schema=False)
def microsoft_login() -> RedirectResponse:
    """Startet den Flow: Redirect zu Microsoft, nonce als httpOnly-Cookie."""
    try:
        url, nonce = start_login(redirect_uri=_redirect_uri())
    except BusinessRuleError as exc:  # u.a. Microsoft-Integration nicht konfiguriert
        return _login_error(str(exc))
    response = RedirectResponse(url)
    response.set_cookie(
        NONCE_COOKIE,
        nonce,
        max_age=600,
        httponly=True,
        secure=_is_https(),
        samesite="lax",  # Lax: der Callback ist ein Top-Level-GET von Microsoft
        path=_cookie_path(),
    )
    return response


@public_router.get("/callback", include_in_schema=False)
def microsoft_callback(
    request: Request,
    session: DatabaseSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    ip = client_ip(
        request.headers.get("cf-connecting-ip"),
        request.headers.get("x-forwarded-for"),
        request.client.host if request.client else None,
    )
    if login_rate_limiter.is_blocked(ip):
        return _login_error("Zu viele Versuche. Bitte in ein paar Minuten erneut versuchen.")
    if error:
        return _login_error(error_description or error)
    if not code or not state:
        return _login_error("Die Microsoft-Anmeldung wurde nicht abgeschlossen.")
    try:
        user, token = complete_login(
            session,
            code=code,
            state=state,
            cookie_nonce=request.cookies.get(NONCE_COOKIE),
            redirect_uri=_redirect_uri(),
        )
    except AuthenticationError as exc:
        login_rate_limiter.record_failure(ip)
        return _login_error(str(exc))
    except BusinessRuleError as exc:  # State/Browser-Bindung, Token-Tausch, Graph-Fehler
        logger.warning("Microsoft-Login fehlgeschlagen: %s", exc)
        return _login_error(str(exc))

    login_rate_limiter.record_success(ip)
    response = RedirectResponse(f"{_frontend_origin()}/sso-complete")
    response.delete_cookie(NONCE_COOKIE, path=_cookie_path())
    response.set_cookie(
        get_settings().auth_cookie_name,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=_is_https(),
        samesite="lax",
        path="/",
    )
    return response
