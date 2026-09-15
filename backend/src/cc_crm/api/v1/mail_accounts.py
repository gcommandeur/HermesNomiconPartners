"""Verwaltung der verbundenen Postfaecher + manueller Abruf.

Durchgaengig AdminUser-geschuetzt: hier liegen die Zugangsdaten aller
Firmen-Postfaecher, das ist keine Funktion fuer normale Nutzer (bestehende,
bewusste Vorgabe - siehe test_non_admin_cannot_list_accounts). Die
Compose-UI (Auftrag "M365-Postfach-Integration") zeigt Nicht-Admins deshalb
keine Postfach-Auswahl an, sondern laesst POST /mail/send serverseitig ueber
MailAccountService.resolve_send_account auf das Standardpostfach schliessen
(account_id=None) - siehe frontend/src/components/crm/mail-compose-modal.tsx.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from fastapi.responses import RedirectResponse

from cc_crm.api.dependencies import AdminUser, DatabaseSession
from cc_crm.core.config import get_settings
from cc_crm.models.enums import MailMatchStatus
from cc_crm.schemas.mail import (
    MailAccountCreate,
    MailAccountRead,
    MailAccountUpdate,
    MailMessageRead,
    MailOAuthStartResult,
    MailSyncResult,
)
from cc_crm.services.mail_accounts import MailAccountService
from cc_crm.services.mail_oauth import handle_oauth_callback, start_oauth_flow
from cc_crm.services.mail_sync import MailSyncService

router = APIRouter(prefix="/mail-accounts")


def _oauth_redirect_uri() -> str:
    """Muss Zeichen-fuer-Zeichen mit der in Entra ID hinterlegten Redirect-
    URI uebereinstimmen (OAuth-Vorgabe) - baut sie aus CC_CRM_CORS_ORIGINS[0]
    (der oeffentlichen App-Domain, Frontend und Backend teilen sich diese
    ueber die DO-App-Platform-Routing-Regel /api/v1) statt sie hier
    zusaetzlich hart zu verdrahten."""
    settings = get_settings()
    origin = str(settings.cors_origins[0]).rstrip("/") if settings.cors_origins else ""
    return f"{origin}{settings.api_prefix}/mail-accounts/oauth/callback"


def _frontend_postfaecher_url(*, connected: str | None = None, error: str | None = None) -> str:
    settings = get_settings()
    origin = str(settings.cors_origins[0]).rstrip("/") if settings.cors_origins else ""
    url = f"{origin}/einstellungen/postfaecher"
    if connected:
        return f"{url}?ms_connected={connected}"
    if error:
        return f"{url}?ms_error={error}"
    return url


@router.get("", response_model=list[MailAccountRead])
def list_mail_accounts(session: DatabaseSession, _admin: AdminUser) -> list[MailAccountRead]:
    accounts = MailAccountService(session).list_accounts()
    return [MailAccountRead.model_validate(account) for account in accounts]


@router.post("", response_model=MailAccountRead, status_code=status.HTTP_201_CREATED)
def create_mail_account(
    payload: MailAccountCreate, session: DatabaseSession, _admin: AdminUser
) -> MailAccountRead:
    account = MailAccountService(session).create(payload)
    return MailAccountRead.model_validate(account)


@router.patch("/{account_id}", response_model=MailAccountRead)
def update_mail_account(
    account_id: uuid.UUID,
    payload: MailAccountUpdate,
    session: DatabaseSession,
    _admin: AdminUser,
) -> MailAccountRead:
    account = MailAccountService(session).update(account_id, payload)
    return MailAccountRead.model_validate(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mail_account(account_id: uuid.UUID, session: DatabaseSession, _admin: AdminUser) -> None:
    MailAccountService(session).delete(account_id)


@router.post("/{account_id}/sync", response_model=MailSyncResult)
def sync_mail_account(
    account_id: uuid.UUID, session: DatabaseSession, _admin: AdminUser
) -> MailSyncResult:
    """Manueller Abruf ("Jetzt abrufen").

    Ein fehlgeschlagener Abruf liefert bewusst 200 mit ok=False statt eines
    HTTP-Fehlers: die Oberflaeche soll den konkreten Grund anzeigen koennen
    (falsche Zugangsdaten vs. Netzwerkproblem, Nutzer-Vorgabe) - bei einem
    5xx bekaeme sie nur die generische Fehlermeldung des globalen
    Error-Handlers.
    """
    account = MailAccountService(session).get(account_id)
    return MailSyncService(session).sync_account(account)


@router.get("/{account_id}/messages", response_model=list[MailMessageRead])
def list_mail_messages(
    account_id: uuid.UUID,
    session: DatabaseSession,
    _admin: AdminUser,
    # Mehrfach angebbar (?match_status=matched&match_status=pending_review),
    # damit die Oberflaeche "alles außer Unbekannt" (ihr Default, um die
    # Liste nicht mit Newslettern/Werbung vollzustopfen) in einer einzigen
    # Anfrage abbilden kann, statt zwei Seiten zusammenzufuehren.
    match_status: Annotated[list[MailMatchStatus] | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[MailMessageRead]:
    """Nachvollziehbare Liste der ueber dieses Konto eingelesenen Mails
    (Postfaecher-Seite) - sortiert nach received_at absteigend, optional
    nach match_status gefiltert."""
    # get() wirft EntityNotFoundError bei unbekannter ID, damit ein
    # falscher/geloeschter Account nicht stillschweigend eine leere Liste
    # liefert.
    MailAccountService(session).get(account_id)
    return MailAccountService(session).list_messages(
        account_id, match_status=match_status, offset=offset, limit=limit
    )


@router.get("/oauth/start", response_model=MailOAuthStartResult)
def start_mail_oauth(admin: AdminUser) -> MailOAuthStartResult:
    """ "Mit Microsoft anmelden"-Button in Einstellungen -> Postfächer -
    liefert die Microsoft-Autorisierungs-URL mit einem signierten `state`
    (traegt admin.id), das Frontend leitet den Browser per
    `window.location.href` dorthin weiter. Normaler authentifizierter
    Aufruf (ueber den Next.js-Proxy, siehe queries.ts::startMicrosoftOAuth) -
    anders als /oauth/callback unten, der direkt von Microsoft angesprungen
    wird und deshalb KEIN Bearer-Token hat."""
    url = start_oauth_flow(redirect_uri=_oauth_redirect_uri(), current_user_id=admin.id)
    return MailOAuthStartResult(authorization_url=url)


@router.get("/oauth/callback", include_in_schema=False)
def mail_oauth_callback(
    session: DatabaseSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    """Redirect-Ziel aus Entra ID - wird DIREKT vom Browser nach dem
    Microsoft-Login/Consent angesprungen, ohne CRM-Login-Cookie (das haengt
    am Frontend-Origin, siehe frontend/src/app/api/proxy/[...path]/
    route.ts). `state` uebernimmt deshalb sowohl CSRF-Schutz als auch die
    Zuordnung zum CRM-Nutzer (siehe integrations/microsoft_graph/
    oauth_state.py). Antwortet IMMER mit einem Redirect zurueck ins
    Frontend statt mit JSON - Gegë soll nach dem Verbinden wieder im CRM
    landen, nicht auf einer nackten Backend-Antwort."""
    if error:
        return RedirectResponse(_frontend_postfaecher_url(error=error_description or error))
    if not code or not state:
        return RedirectResponse(_frontend_postfaecher_url(error="missing_code_or_state"))

    try:
        account = handle_oauth_callback(
            session, code=code, state=state, redirect_uri=_oauth_redirect_uri()
        )
    except Exception as exc:  # noqa: BLE001 - jeder Fehler landet als lesbare Meldung im Frontend
        return RedirectResponse(_frontend_postfaecher_url(error=str(exc)[:200]))

    return RedirectResponse(_frontend_postfaecher_url(connected=account.address))
