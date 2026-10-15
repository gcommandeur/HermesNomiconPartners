"""Claude-Vorschlaege mit Freigabe-Pflicht (Arbeitsplan 2, Q3).

Claude (MCP-Werkzeuge `propose_*`) legt hier NUR Vorschlaege an. Eine Notiz, eine
Aufgabe oder ein Mail-Entwurf entsteht erst, wenn ein Mensch den Vorschlag in
Hermes freigibt - und eine Mail wird auch dann nie von hier gesendet: der Entwurf
oeffnet vorbefuellt im Mail-Fenster, das Senden macht der Mensch.

Dieses Modul (und mcp_server.py) importiert bewusst KEINEN Sende-Service
(mail_send, due_reminders, outreach_sequences); ein Test sichert das ab.

Freigeben/Ablehnen duerfen der Schluessel-Besitzer (Ersteller), dessen Teamleiter
und Admins. Fremde sehen den Vorschlag nicht (404)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from cc_crm.core.config import get_settings
from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.ai_proposal import AiProposal
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.contact_person import ContactPerson
from cc_crm.models.user import User
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.schemas.ai_proposal import PAYLOAD_MODELS, AiProposalRead
from cc_crm.schemas.note import NoteCreate
from cc_crm.schemas.task import TaskCreate
from cc_crm.services.notes import NoteService
from cc_crm.services.tasks import TaskService

MAX_PENDING_PER_USER = 100
CLAUDE_NOTE_PREFIX = "[per Claude] "
CLAUDE_TASK_SUFFIX = "\n\n(Vorschlag von Claude, von einem Menschen freigegeben)"

_TARGET_MODELS: dict[str, type] = {
    "candidate": Candidate,
    "client": ClientCompany,
    "contact": ContactPerson,
}


def _normalize_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    model = PAYLOAD_MODELS.get(kind)
    if model is None:
        raise BusinessRuleError("Unbekannte Vorschlagsart.")
    try:
        return model.model_validate(payload).model_dump(mode="json", exclude_none=True)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise BusinessRuleError(
            f"Ungueltiger Vorschlag ({'.'.join(str(p) for p in first['loc'])}: {first['msg']})."
        ) from exc


class AiProposalService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit_logs = AuditLogRepository(session)

    # --- Anlegen (nur ueber MCP) -------------------------------------------

    def create(
        self,
        *,
        creator: User,
        kind: str,
        payload: dict[str, Any],
        target_type: str | None,
        target_id: uuid.UUID | None,
    ) -> AiProposal:
        if kind in ("note", "mail_draft") and (target_type is None or target_id is None):
            raise BusinessRuleError("Dieser Vorschlag braucht ein Bezugsobjekt.")
        if kind == "mail_draft" and target_type not in ("candidate", "client", "contact"):
            raise BusinessRuleError(
                "Mail-Entwuerfe gehen an einen Kandidaten, einen Kunden oder einen Kontakt."
            )
        if kind == "note" and target_type not in ("candidate", "client"):
            raise BusinessRuleError("Notizen gibt es nur zu Kandidaten und Kunden.")
        if target_type is not None:
            model = _TARGET_MODELS.get(target_type)
            if model is None or target_id is None or self.session.get(model, target_id) is None:
                raise BusinessRuleError("Bezugsobjekt nicht gefunden.")
        pending = self.session.scalar(
            select(func.count())
            .select_from(AiProposal)
            .where(AiProposal.created_by_user_id == creator.id, AiProposal.status == "pending")
        )
        if (pending or 0) >= MAX_PENDING_PER_USER:
            raise BusinessRuleError(
                f"Es warten bereits {MAX_PENDING_PER_USER} offene Vorschlaege - "
                "bitte erst bearbeiten."
            )
        proposal = AiProposal(
            kind=kind,
            status="pending",
            target_type=target_type,
            target_id=target_id,
            payload=_normalize_payload(kind, payload),
            created_by_user_id=creator.id,
        )
        self.session.add(proposal)
        self.session.flush()
        self._audit(proposal, "ai_proposal_created", creator.email)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    # --- Sichtbarkeit ------------------------------------------------------

    def _visible_filter(self, user: User):  # type: ignore[no-untyped-def]
        if user.is_admin:
            return None
        team_ids = select(User.id).where(User.manager_id == user.id) if user.is_team_lead else None
        if team_ids is not None:
            return or_(
                AiProposal.created_by_user_id == user.id,
                AiProposal.created_by_user_id.in_(team_ids),
            )
        return AiProposal.created_by_user_id == user.id

    def list_visible(
        self, user: User, *, status: str | None = None, limit: int = 100
    ) -> list[AiProposal]:
        statement = select(AiProposal).order_by(AiProposal.created_at.desc()).limit(limit)
        visible = self._visible_filter(user)
        if visible is not None:
            statement = statement.where(visible)
        if status:
            statement = statement.where(AiProposal.status == status)
        return list(self.session.scalars(statement))

    def get(self, user: User, proposal_id: uuid.UUID) -> AiProposal:
        proposal = self.session.get(AiProposal, proposal_id)
        if proposal is None:
            raise EntityNotFoundError("Vorschlag nicht gefunden")
        if not self._may_see(user, proposal):
            raise EntityNotFoundError("Vorschlag nicht gefunden")
        return proposal

    def _may_see(self, user: User, proposal: AiProposal) -> bool:
        if user.is_admin or proposal.created_by_user_id == user.id:
            return True
        if user.is_team_lead:
            creator = self.session.get(User, proposal.created_by_user_id)
            return creator is not None and creator.manager_id == user.id
        return False

    def pending_count(self, user: User) -> int:
        statement = (
            select(func.count()).select_from(AiProposal).where(AiProposal.status == "pending")
        )
        visible = self._visible_filter(user)
        if visible is not None:
            statement = statement.where(visible)
        return int(self.session.scalar(statement) or 0)

    # --- Entscheiden -------------------------------------------------------

    def approve(
        self, user: User, proposal_id: uuid.UUID, edited_payload: dict[str, Any] | None
    ) -> AiProposal:
        proposal = self.get(user, proposal_id)
        if proposal.status != "pending":
            raise BusinessRuleError("Dieser Vorschlag ist bereits entschieden.")
        if edited_payload is not None:
            proposal.payload = _normalize_payload(proposal.kind, edited_payload)
        payload = proposal.payload
        # Nur Notiz und Aufgabe werden angelegt; ein Mail-Entwurf wird NIE gesendet -
        # er oeffnet im Frontend vorbefuellt, der Mensch klickt "Senden".
        candidate_id = proposal.target_id if proposal.target_type == "candidate" else None
        client_id = proposal.target_id if proposal.target_type == "client" else None
        if proposal.kind == "note":
            note = NoteService(self.session).create(
                NoteCreate(
                    candidate_id=candidate_id,
                    client_company_id=client_id,
                    body=CLAUDE_NOTE_PREFIX + payload["text"],
                ),
                created_by_user_id=user.id,
            )
            proposal.result_entity_type, proposal.result_entity_id = "note", note.id
        elif proposal.kind == "task":
            task = TaskService(self.session).create(
                TaskCreate(
                    title=payload["title"],
                    description=(payload.get("description") or "").strip() + CLAUDE_TASK_SUFFIX,
                    due_at=(
                        datetime.fromisoformat(payload["due_at"]) if payload.get("due_at") else None
                    ),
                    candidate_id=candidate_id,
                    client_company_id=client_id,
                    owner_user_id=proposal.created_by_user_id,
                )
            )
            proposal.result_entity_type, proposal.result_entity_id = "task", task.id
        proposal.status = "approved"
        proposal.decided_by_user_id = user.id
        proposal.decided_at = datetime.now(UTC)
        self._audit(proposal, "ai_proposal_approved", user.email)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    def reject(self, user: User, proposal_id: uuid.UUID, note: str | None) -> AiProposal:
        proposal = self.get(user, proposal_id)
        if proposal.status != "pending":
            raise BusinessRuleError("Dieser Vorschlag ist bereits entschieden.")
        proposal.status = "rejected"
        proposal.decided_by_user_id = user.id
        proposal.decided_at = datetime.now(UTC)
        proposal.decision_note = note
        self._audit(proposal, "ai_proposal_rejected", user.email)
        self.session.commit()
        self.session.refresh(proposal)
        return proposal

    # --- Darstellung -------------------------------------------------------

    def to_read(self, proposals: list[AiProposal]) -> list[AiProposalRead]:
        names: dict[uuid.UUID, str] = {}
        user_ids = {p.created_by_user_id for p in proposals}
        for user in self.session.scalars(select(User).where(User.id.in_(user_ids))):
            names[user.id] = user.display_name or user.email
        result = []
        for proposal in proposals:
            label, email = self._target_info(proposal)
            result.append(
                AiProposalRead.model_validate(proposal).model_copy(
                    update={
                        "target_label": label,
                        "recipient_email": email if proposal.kind == "mail_draft" else None,
                        "created_by_name": names.get(proposal.created_by_user_id),
                    }
                )
            )
        return result

    def _target_info(self, proposal: AiProposal) -> tuple[str | None, str | None]:
        if proposal.target_type is None or proposal.target_id is None:
            return None, None
        model = _TARGET_MODELS.get(proposal.target_type)
        entity = self.session.get(model, proposal.target_id) if model else None
        if entity is None:
            return None, None
        if isinstance(entity, ClientCompany):
            return entity.name, None
        return f"{entity.first_name} {entity.last_name}".strip(), getattr(entity, "email", None)

    def _audit(self, proposal: AiProposal, action: str, changed_by: str) -> None:
        # Nur Art und Bezugsobjekt-Typ - nie der vorgeschlagene Text.
        self.audit_logs.create(
            {
                "entity_type": "ai_proposal",
                "entity_id": proposal.id,
                "action": action,
                "changed_by": changed_by,
                "new_values": {"kind": proposal.kind, "target_type": proposal.target_type},
            }
        )


def ai_enabled() -> bool:
    return bool(get_settings().ai_enabled)
