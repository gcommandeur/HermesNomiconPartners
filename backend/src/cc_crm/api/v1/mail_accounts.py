"""Verwaltung der verbundenen Postfaecher + manueller Abruf.

Durchgaengig AdminUser-geschuetzt: hier liegen die Zugangsdaten aller
Firmen-Postfaecher, das ist keine Funktion fuer normale Nutzer.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from cc_crm.api.dependencies import AdminUser, DatabaseSession
from cc_crm.models.enums import MailMatchStatus
from cc_crm.schemas.mail import (
    MailAccountCreate,
    MailAccountRead,
    MailAccountUpdate,
    MailMessageRead,
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
