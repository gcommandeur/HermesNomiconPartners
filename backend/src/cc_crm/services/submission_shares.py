import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.submission_share import SubmissionShare
from cc_crm.models.user import User
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.schemas.submission import SubmissionShareRead


class SubmissionShareService:
    """Gezieltes Teilen eines einzelnen Prozesses mit einem Kollegen (volle
    Rechte, kein Berechtigungslevel). Die Zugriffspruefung "darf den Prozess
    sehen" erledigt der API-Layer (SubmissionAccess) - hier nur die
    Fachregeln und das Audit-Log."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit_logs = AuditLogRepository(session)

    def _submission(self, submission_id: uuid.UUID) -> CandidateSubmission:
        submission = self.session.get(CandidateSubmission, submission_id)
        if submission is None:
            raise EntityNotFoundError("CandidateSubmission not found")
        return submission

    def _label(self, user_id: uuid.UUID | None) -> str | None:
        if user_id is None:
            return None
        user = self.session.get(User, user_id)
        return (user.display_name or user.email) if user else None

    def to_read(self, share: SubmissionShare) -> SubmissionShareRead:
        return SubmissionShareRead(
            id=share.id,
            submission_id=share.submission_id,
            shared_with_user_id=share.shared_with_user_id,
            shared_with_name=self._label(share.shared_with_user_id),
            created_by_user_id=share.created_by_user_id,
            created_by_name=self._label(share.created_by_user_id),
            created_at=share.created_at,
        )

    def list_for_submission(self, submission_id: uuid.UUID) -> list[SubmissionShare]:
        self._submission(submission_id)
        return list(
            self.session.scalars(
                select(SubmissionShare)
                .where(SubmissionShare.submission_id == submission_id)
                .order_by(SubmissionShare.created_at)
            ).all()
        )

    def create(
        self, submission_id: uuid.UUID, shared_with_user_id: uuid.UUID, current_user: User
    ) -> SubmissionShare:
        """Doppelte Freigabe an dieselbe Person ist idempotent: die bestehende
        Freigabe wird zurueckgegeben (kein Fehler, kein zweiter Audit-Eintrag) -
        das Ergebnis ("Person hat Zugriff") ist das, was der Aufrufer wollte."""
        submission = self._submission(submission_id)
        if shared_with_user_id == current_user.id:
            raise BusinessRuleError("Du kannst einen Prozess nicht mit dir selbst teilen.")
        if shared_with_user_id == submission.owner_user_id:
            raise BusinessRuleError("Die Person ist bereits Eigentuemer des Prozesses.")
        target = self.session.get(User, shared_with_user_id)
        if target is None or not target.is_active:
            raise BusinessRuleError("Nutzer nicht gefunden oder deaktiviert.")
        existing = self.session.scalar(
            select(SubmissionShare).where(
                SubmissionShare.submission_id == submission_id,
                SubmissionShare.shared_with_user_id == shared_with_user_id,
            )
        )
        if existing is not None:
            return existing
        share = SubmissionShare(
            submission_id=submission_id,
            shared_with_user_id=shared_with_user_id,
            created_by_user_id=current_user.id,
        )
        self.session.add(share)
        self.session.flush()
        self.audit_logs.create(
            {
                "entity_type": "candidate_submission",
                "entity_id": submission_id,
                "action": "share_added",
                "changed_by": current_user.email,
                "new_values": {"shared_with_user_id": str(shared_with_user_id)},
            }
        )
        self.session.commit()
        return share

    def get(self, submission_id: uuid.UUID, share_id: uuid.UUID) -> SubmissionShare:
        share = self.session.get(SubmissionShare, share_id)
        if share is None or share.submission_id != submission_id:
            raise EntityNotFoundError("Freigabe nicht gefunden")
        return share

    def delete(self, submission_id: uuid.UUID, share_id: uuid.UUID, current_user: User) -> None:
        share = self.get(submission_id, share_id)
        self.session.delete(share)
        self.audit_logs.create(
            {
                "entity_type": "candidate_submission",
                "entity_id": submission_id,
                "action": "share_removed",
                "changed_by": current_user.email,
                "old_values": {"shared_with_user_id": str(share.shared_with_user_id)},
            }
        )
        self.session.commit()
