"""Verwaltung der verbundenen Postfaecher + manueller Abruf.

Durchgaengig AdminUser-geschuetzt: hier liegen die Zugangsdaten aller
Firmen-Postfaecher, das ist keine Funktion fuer normale Nutzer.
"""

import uuid

from fastapi import APIRouter, status

from cc_crm.api.dependencies import AdminUser, DatabaseSession
from cc_crm.schemas.mail import (
    MailAccountCreate,
    MailAccountRead,
    MailAccountUpdate,
    MailSyncResult,
)
from cc_crm.services.mail_accounts import MailAccountService
from cc_crm.services.mail_sync import MailSyncService

router = APIRouter(prefix="/mail-accounts")


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
def delete_mail_account(
    account_id: uuid.UUID, session: DatabaseSession, _admin: AdminUser
) -> None:
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
