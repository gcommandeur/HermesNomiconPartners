"""Mein Postfach: persoenliche IMAP/SMTP-Konten des angemeldeten Nutzers.

Jeder sieht und aendert nur die EIGENEN Konten (fremde = 404); die
Admin-Verwaltung der gemeinsamen Postfaecher (api/v1/mail_accounts.py) bleibt
unveraendert."""

import uuid

from fastapi import APIRouter, status

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.core.errors import BusinessRuleError
from cc_crm.models.enums import MailMatchStatus
from cc_crm.models.mail import MailAccount
from cc_crm.schemas.mail import (
    MailConnectionTestRequest,
    MailConnectionTestResult,
    MailMessageRead,
    MailSyncResult,
    MyMailAccountCreate,
    MyMailAccountRead,
    MyMailAccountUpdate,
)
from cc_crm.services.mail_accounts import MailAccountService
from cc_crm.services.mail_sync import MailSyncService
from cc_crm.services.my_mail_accounts import MyMailAccountService

router = APIRouter(prefix="/me/mail-accounts")


def _read(account: MailAccount, user: CurrentUser) -> MyMailAccountRead:
    return MyMailAccountRead.model_validate(account).model_copy(
        update={"is_default_sender": user.default_send_account_id == account.id}
    )


@router.get("", response_model=list[MyMailAccountRead])
def list_my_mail_accounts(
    session: DatabaseSession, current_user: CurrentUser
) -> list[MyMailAccountRead]:
    service = MyMailAccountService(session, current_user)
    return [_read(item, current_user) for item in service.list()]


@router.post("", response_model=MyMailAccountRead, status_code=status.HTTP_201_CREATED)
def create_my_mail_account(
    payload: MyMailAccountCreate, session: DatabaseSession, current_user: CurrentUser
) -> MyMailAccountRead:
    return _read(MyMailAccountService(session, current_user).create(payload), current_user)


@router.post("/test", response_model=MailConnectionTestResult)
def test_connection_before_saving(
    payload: MailConnectionTestRequest, current_user: CurrentUser
) -> MailConnectionTestResult:
    """Zugangsdaten pruefen (IMAP-Login, SMTP-Login), ohne etwas zu speichern oder zu senden."""
    return MyMailAccountService.test_unsaved(payload)


@router.patch("/{account_id}", response_model=MyMailAccountRead)
def update_my_mail_account(
    account_id: uuid.UUID,
    payload: MyMailAccountUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> MyMailAccountRead:
    account = MyMailAccountService(session, current_user).update(account_id, payload)
    return _read(account, current_user)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_mail_account(
    account_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> None:
    MyMailAccountService(session, current_user).delete(account_id)


@router.post("/{account_id}/test", response_model=MailConnectionTestResult)
def test_my_mail_account(
    account_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> MailConnectionTestResult:
    return MyMailAccountService(session, current_user).test_saved(account_id)


@router.post("/{account_id}/default", response_model=MyMailAccountRead)
def set_default_sender(
    account_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> MyMailAccountRead:
    account = MyMailAccountService(session, current_user).set_default(account_id)
    return _read(account, current_user)


@router.post("/{account_id}/sync", response_model=MailSyncResult)
def sync_my_mail_account(
    account_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> MailSyncResult:
    account = MyMailAccountService(session, current_user).get(account_id)
    if not account.sync_enabled:
        raise BusinessRuleError(
            "Der Posteingang-Abruf ist fuer dieses Postfach ausgeschaltet (nur Versand)."
        )
    return MailSyncService(session).sync_account(account)


@router.get("/{account_id}/messages", response_model=list[MailMessageRead])
def list_my_mail_messages(
    account_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
    match_status: list[MailMatchStatus] | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[MailMessageRead]:
    """Posteingang eines persoenlichen Kontos: nur fuer den Besitzer lesbar."""
    MyMailAccountService(session, current_user).get(account_id)
    return MailAccountService(session).list_messages(
        account_id, match_status=match_status, offset=offset, limit=min(max(limit, 1), 200)
    )
