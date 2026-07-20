import secrets
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError, PermissionDeniedError
from cc_crm.models.user import User
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.schemas.user import UserAdminUpdate


class UserService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit_logs = AuditLogRepository(session)

    def get(self, user_id: uuid.UUID) -> User:
        user = self.session.get(User, user_id)
        if user is None:
            raise EntityNotFoundError("User not found")
        return user

    def list_all(self) -> Sequence[User]:
        return self.session.scalars(select(User).order_by(User.email)).all()

    def update_admin_fields(
        self, user_id: uuid.UUID, payload: UserAdminUpdate, current_user: User
    ) -> User:
        """Nur fuer Admins aufrufbar (siehe API-Layer) - verhindert
        zusaetzlich, dass sich ein Admin versehentlich selbst das Admin-Recht
        entzieht (sonst waere ohne einen zweiten Admin niemand mehr in der
        Lage, es zurueckzugeben)."""
        user = self.get(user_id)
        if (
            user.id == current_user.id
            and payload.is_admin is False
            and current_user.is_admin
        ):
            raise BusinessRuleError(
                "Du kannst dir dein eigenes Admin-Recht nicht selbst entziehen."
            )
        old_values = {"role": user.role, "is_active": user.is_active}
        changed = False
        if payload.is_admin is not None:
            user.role = "admin" if payload.is_admin else "member"
            changed = True
        if payload.is_active is not None:
            user.is_active = payload.is_active
            changed = True
        if changed:
            # Sicherheitsrelevant (wer hat wem welche Rechte gegeben/entzogen) -
            # deshalb explizit geloggt, anders als normale Feldaenderungen an
            # den Kernentitaeten (siehe Modul-Docstring Punkt 2 des Auftrags).
            self.audit_logs.create(
                {
                    "entity_type": "user",
                    "entity_id": user.id,
                    "action": "admin_fields_changed",
                    "changed_by": current_user.email,
                    "old_values": old_values,
                    "new_values": {"role": user.role, "is_active": user.is_active},
                }
            )
        self.session.commit()
        return user

    def rotate_calendar_feed_token(self, user_id: uuid.UUID, current_user: User) -> User:
        user = self.get(user_id)
        if not current_user.is_admin and user.id != current_user.id:
            raise PermissionDeniedError(
                "Nur der Nutzer selbst oder ein Admin kann den Feed-Token neu generieren."
            )
        user.calendar_feed_token = secrets.token_urlsafe(32)
        self.audit_logs.create(
            {
                "entity_type": "user",
                "entity_id": user.id,
                "action": "calendar_feed_token_rotated",
                "changed_by": current_user.email,
            }
        )
        self.session.commit()
        return user
