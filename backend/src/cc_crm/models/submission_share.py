import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SubmissionShare(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Gezielte Freigabe EINES Prozesses an einen Kollegen (Vertretung,
    Vier-Augen-Pruefung). Gewaehrt vollen Zugriff (lesen und schreiben) -
    bewusst kein Berechtigungslevel. Rein additiv zur Sichtbarkeit ueber
    Eigentuemer/Team (api/dependencies.py::process_owner_scope)."""

    __tablename__ = "submission_shares"
    __table_args__ = (
        UniqueConstraint("submission_id", "shared_with_user_id"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_submissions.id", ondelete="CASCADE"), index=True
    )
    shared_with_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
