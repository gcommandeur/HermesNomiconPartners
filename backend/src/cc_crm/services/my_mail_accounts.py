"""Persoenliche Postfaecher ("Mein Postfach"): jeder Nutzer verwaltet NUR seine eigenen.

Fremd und nicht vorhanden liefern dasselbe 404. Passwoerter werden sofort
verschluesselt und nie zurueckgegeben. Persoenliche Konten sind nie CV-Out-Standard
und starten ohne Posteingangs-Abruf (nur Versand)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.enums import MailAccountProvider
from cc_crm.models.mail import MailAccount
from cc_crm.models.user import User
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.schemas.mail import (
    MailConnectionTestRequest,
    MailConnectionTestResult,
    MyMailAccountCreate,
    MyMailAccountUpdate,
)
from cc_crm.services.mail_connection_test import MailCredentials, check_connection
from cc_crm.services.mail_credentials import decrypt_password, encrypt_password


class MyMailAccountService:
    def __init__(self, session: Session, user: User) -> None:
        self.session = session
        self.user = user
        self.audit_logs = AuditLogRepository(session)

    def list(self) -> list[MailAccount]:
        return list(
            self.session.scalars(
                select(MailAccount)
                .where(MailAccount.owner_user_id == self.user.id)
                .order_by(MailAccount.address)
            )
        )

    def get(self, account_id: uuid.UUID) -> MailAccount:
        account = self.session.get(MailAccount, account_id)
        if account is None or account.owner_user_id != self.user.id:
            raise EntityNotFoundError("Postfach nicht gefunden")
        return account

    def _get_imap(self, account_id: uuid.UUID) -> MailAccount:
        account = self.get(account_id)
        if account.provider != MailAccountProvider.IMAP_SMTP:
            raise BusinessRuleError(
                "Dieses Postfach ist ueber Microsoft verbunden - bitte unter "
                "'Outlook & Teams' verwalten."
            )
        return account

    def create(self, payload: MyMailAccountCreate) -> MailAccount:
        address = str(payload.address).lower()
        if self.session.scalar(select(MailAccount).where(MailAccount.address == address)):
            raise BusinessRuleError(f"Postfach {address} ist bereits verbunden.")
        data = payload.model_dump(exclude={"password", "address"})
        account = MailAccount(
            address=address,
            encrypted_password=encrypt_password(payload.password),
            owner_user_id=self.user.id,
            sync_enabled=False,
            default_for_cv_out=False,
            provider=MailAccountProvider.IMAP_SMTP,
            **data,
        )
        self.session.add(account)
        self.session.flush()
        self._audit(account, "created")
        if self.user.default_send_account_id is None:
            self.user.default_send_account_id = account.id
        self.session.commit()
        self.session.refresh(account)
        return account

    def update(self, account_id: uuid.UUID, payload: MyMailAccountUpdate) -> MailAccount:
        account = self._get_imap(account_id)
        data = payload.model_dump(exclude_unset=True, exclude={"password"})
        if payload.password is not None:
            account.encrypted_password = encrypt_password(payload.password)
        for field, value in data.items():
            setattr(account, field, value)
        if account.is_active is False and self.user.default_send_account_id == account.id:
            self.user.default_send_account_id = None
        self._audit(account, "updated")
        self.session.commit()
        self.session.refresh(account)
        return account

    def delete(self, account_id: uuid.UUID) -> None:
        account = self.get(account_id)
        if self.user.default_send_account_id == account.id:
            self.user.default_send_account_id = None
        self._audit(account, "deleted")
        self.session.delete(account)
        self.session.commit()

    def set_default(self, account_id: uuid.UUID) -> MailAccount:
        account = self.get(account_id)
        if not account.is_active:
            raise BusinessRuleError("Ein deaktiviertes Postfach kann kein Standard-Absender sein.")
        self.user.default_send_account_id = account.id
        self.session.commit()
        return account

    def test_saved(self, account_id: uuid.UUID) -> MailConnectionTestResult:
        account = self._get_imap(account_id)
        if not (account.imap_host and account.smtp_host and account.username):
            raise BusinessRuleError("Zugangsdaten unvollstaendig.")
        password = decrypt_password(account.encrypted_password or "")
        return check_connection(
            MailCredentials(
                imap_host=account.imap_host,
                imap_port=account.imap_port,
                imap_use_ssl=account.imap_use_ssl,
                smtp_host=account.smtp_host,
                smtp_port=account.smtp_port,
                smtp_use_ssl=account.smtp_use_ssl,
                username=account.username,
                password=password,
            )
        )

    @staticmethod
    def test_unsaved(payload: MailConnectionTestRequest) -> MailConnectionTestResult:
        return check_connection(MailCredentials(**payload.model_dump()))

    def _audit(self, account: MailAccount, action: str) -> None:
        # Nie Passwort oder Zugangsdaten ins Audit-Log - nur dass etwas passiert ist.
        self.audit_logs.create(
            {
                "entity_type": "mail_account",
                "entity_id": account.id,
                "action": f"personal_{action}",
                "changed_by": self.user.email,
            }
        )
