"""Verwaltung der verbundenen Postfaecher (Admin-Maske "E-Mails & Konten").

Passwoerter werden hier beim Anlegen/Aendern sofort verschluesselt (siehe
mail_credentials.py) und verlassen den Service nie wieder im Klartext.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.mail import MailAccount
from cc_crm.models.user import User
from cc_crm.schemas.mail import MailAccountCreate, MailAccountUpdate
from cc_crm.services.mail_credentials import encrypt_password


class MailAccountService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_accounts(self) -> list[MailAccount]:
        return list(
            self.session.scalars(select(MailAccount).order_by(MailAccount.address)).all()
        )

    def get(self, account_id: uuid.UUID) -> MailAccount:
        account = self.session.get(MailAccount, account_id)
        if account is None:
            raise EntityNotFoundError("Postfach nicht gefunden")
        return account

    def create(self, payload: MailAccountCreate) -> MailAccount:
        existing = self.session.scalar(
            select(MailAccount).where(MailAccount.address == str(payload.address))
        )
        if existing is not None:
            raise BusinessRuleError(f"Postfach {payload.address} ist bereits verbunden.")

        data = payload.model_dump(exclude={"password", "address"})
        account = MailAccount(
            address=str(payload.address),
            # Verschluesselung passiert VOR dem ersten session.add - so
            # landet auch bei einem Fehler danach nie ein Klartext-Passwort
            # in der Session.
            encrypted_password=encrypt_password(payload.password),
            **data,
        )
        self.session.add(account)
        if account.default_for_cv_out:
            self._clear_other_defaults(account)
        self.session.commit()
        self.session.refresh(account)
        return account

    def update(self, account_id: uuid.UUID, payload: MailAccountUpdate) -> MailAccount:
        account = self.get(account_id)
        data = payload.model_dump(exclude_unset=True, exclude={"password"})

        if payload.password is not None:
            account.encrypted_password = encrypt_password(payload.password)

        for field, value in data.items():
            setattr(account, field, value)

        if data.get("default_for_cv_out"):
            self._clear_other_defaults(account)

        self.session.commit()
        self.session.refresh(account)
        return account

    def delete(self, account_id: uuid.UUID) -> None:
        account = self.get(account_id)
        self.session.delete(account)
        self.session.commit()

    def _clear_other_defaults(self, account: MailAccount) -> None:
        """Nur EIN Postfach darf CV-OUT-Standard sein - beim Setzen wird das
        Flag bei allen anderen entfernt. Ohne das haette der Versand bei
        mehreren markierten Konten ein nichtdeterministisches Ergebnis."""
        others = self.session.scalars(
            select(MailAccount).where(MailAccount.default_for_cv_out.is_(True))
        ).all()
        for other in others:
            if other.id != account.id:
                other.default_for_cv_out = False

    def resolve_send_account(self, user: User) -> MailAccount | None:
        """Standard-Absenderpostfach fuer einen Nutzer.

        Reihenfolge laut Nutzer-Vorgabe: persoenlicher Override
        (User.default_send_account_id) -> globales default_for_cv_out ->
        None (dann muss in der Versand-Maske manuell gewaehlt werden).
        Inaktive Postfaecher werden uebersprungen, damit ein abgeschaltetes
        Konto nicht stillschweigend als Absender vorgeschlagen wird.
        """
        if user.default_send_account_id is not None:
            personal = self.session.get(MailAccount, user.default_send_account_id)
            if personal is not None and personal.is_active:
                return personal
        return self.session.scalar(
            select(MailAccount).where(
                MailAccount.default_for_cv_out.is_(True),
                MailAccount.is_active.is_(True),
            )
        )
