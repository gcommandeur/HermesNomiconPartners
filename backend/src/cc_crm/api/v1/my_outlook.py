"""Outlook-Verbindung des angemeldeten Nutzers (Status, Trennen).

Verbunden wird beim "Mit Microsoft anmelden" (services/microsoft_login.py); hier
sieht jede:r die eigene Verbindung und kann sie loeschen. Es gibt nie Zugriff auf
fremde Postfaecher."""

from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel
from sqlalchemy import select

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.models.enums import MailAccountOAuthStatus, MailAccountProvider
from cc_crm.models.mail import MailAccount
from cc_crm.repositories.recruiting import AuditLogRepository

router = APIRouter(prefix="/me/outlook")


class OutlookStatus(BaseModel):
    state: Literal["not_connected", "connected", "needs_reconnect"]
    address: str | None = None


def _own_account(session: DatabaseSession, user_id: object) -> MailAccount | None:
    return session.scalar(
        select(MailAccount).where(
            MailAccount.provider == MailAccountProvider.MICROSOFT_GRAPH,
            MailAccount.oauth_connected_by_user_id == user_id,
            MailAccount.is_active.is_(True),
        )
    )


@router.get("", response_model=OutlookStatus)
def outlook_status(session: DatabaseSession, current_user: CurrentUser) -> OutlookStatus:
    account = _own_account(session, current_user.id)
    if account is None:
        return OutlookStatus(state="not_connected")
    if account.oauth_status == MailAccountOAuthStatus.NEEDS_RECONNECT:
        return OutlookStatus(state="needs_reconnect", address=account.address)
    return OutlookStatus(state="connected", address=account.address)


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_outlook(session: DatabaseSession, current_user: CurrentUser) -> None:
    """Trennt NUR die eigene Verbindung: Token wird geloescht, das Postfach
    inaktiv gesetzt (bereits abgerufene Mails bleiben erhalten)."""
    account = _own_account(session, current_user.id)
    if account is None:
        return
    account.encrypted_oauth_refresh_token = None
    account.oauth_status = MailAccountOAuthStatus.NEEDS_RECONNECT
    account.oauth_connected_by_user_id = None
    account.is_active = False
    if current_user.default_send_account_id == account.id:
        current_user.default_send_account_id = None
    AuditLogRepository(session).create(
        {
            "entity_type": "mail_account",
            "entity_id": account.id,
            "action": "outlook_disconnected",
            "changed_by": current_user.email,
        }
    )
    session.commit()
