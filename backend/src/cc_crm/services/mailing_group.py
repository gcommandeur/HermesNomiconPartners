import uuid
from typing import Any

from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.mailing_group import MailingGroup
from cc_crm.repositories.mailing_group import MailingGroupRepository
from cc_crm.schemas.mailing_group import (
    MailingGroupCreate,
    MailingGroupMergeRequest,
    MailingGroupUpdate,
)
from cc_crm.services.base import CrudService


def _dedupe_key(recipient: dict[str, Any]) -> str:
    """E-Mail-Adresse (kleingeschrieben) als Dedupe-Schluessel; Empfaenger
    ohne E-Mail werden über kind+id dedupliziert (koennen nicht per E-Mail
    verglichen werden, sollen aber auch nicht durch Mehrfachauswahl doppelt
    in derselben Gruppe landen)."""
    email = recipient.get("email")
    if email:
        return f"email:{email.strip().lower()}"
    return f"{recipient.get('kind')}:{recipient.get('id')}"


class MailingGroupService(CrudService[MailingGroup, MailingGroupCreate, MailingGroupUpdate]):
    def __init__(self, session: Session) -> None:
        repository = MailingGroupRepository(session)
        super().__init__(session, repository, "MailingGroup")
        self.groups = repository

    def merge(self, payload: MailingGroupMergeRequest) -> MailingGroup:
        """Vereinigt die recipients mehrerer Gruppen, dedupliziert nach
        E-Mail-Adresse, und speichert das Ergebnis als neue Gruppe oder
        ueberschreibt eine bestehende (payload.overwrite_group_id)."""
        merged: dict[str, dict[str, Any]] = {}
        for group_id in payload.group_ids:
            group = self.groups.get(uuid.UUID(group_id))
            if group is None:
                raise EntityNotFoundError(f"MailingGroup {group_id} not found")
            for recipient in group.recipients:
                merged[_dedupe_key(recipient)] = recipient

        recipients = list(merged.values())

        if payload.overwrite_group_id:
            existing = self.groups.get(uuid.UUID(payload.overwrite_group_id))
            if existing is None:
                raise EntityNotFoundError(f"MailingGroup {payload.overwrite_group_id} not found")
            updated = self.groups.update(
                existing, {"name": payload.target_name, "recipients": recipients}
            )
            self.session.commit()
            return updated

        try:
            created = self.groups.create({"name": payload.target_name, "recipients": recipients})
            self.session.commit()
            return created
        except Exception as exception:
            self.session.rollback()
            raise BusinessRuleError(
                f"Gruppe '{payload.target_name}' konnte nicht angelegt werden "
                "(Name evtl. schon vergeben)."
            ) from exception
