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
        new_role: str | None = None
        if payload.role is not None:
            new_role = payload.role
        elif payload.is_admin is True:
            new_role = "admin"
        elif payload.is_admin is False and user.is_admin:
            new_role = "member"
        if (
            user.id == current_user.id
            and current_user.is_admin
            and new_role is not None
            and new_role != "admin"
        ):
            raise BusinessRuleError(
                "Du kannst dir dein eigenes Admin-Recht nicht selbst entziehen."
            )
        old_values = {
            "role": user.role,
            "is_active": user.is_active,
            "manager_id": str(user.manager_id) if user.manager_id else None,
        }
        changed = False
        if new_role is not None:
            user.role = new_role
            changed = True
        if payload.is_active is not None:
            user.is_active = payload.is_active
            changed = True
        if "manager_id" in payload.model_fields_set:
            self._assign_manager(user, payload.manager_id)
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
                    "new_values": {
                        "role": user.role,
                        "is_active": user.is_active,
                        "manager_id": str(user.manager_id) if user.manager_id else None,
                    },
                }
            )
        self.session.commit()
        return user

    def _assign_manager(self, user: User, manager_id: uuid.UUID | None) -> None:
        """Teamleiter-Zuordnung setzen/aufheben. Bewusst einstufig und ohne
        Zyklus-Pruefung (Teamleiter sieht nur seine DIREKTEN Mitarbeiter, siehe
        api/dependencies.py::process_owner_scope). Die Zuordnung wirkt nur,
        wenn der Zugeordnete role="team_lead" hat."""
        if manager_id is None:
            user.manager_id = None
            return
        if manager_id == user.id:
            raise BusinessRuleError("Ein Nutzer kann nicht sein eigener Teamleiter sein.")
        manager = self.session.get(User, manager_id)
        if manager is None:
            raise EntityNotFoundError("Teamleiter nicht gefunden")
        if not manager.is_active:
            raise BusinessRuleError("Der Teamleiter ist deaktiviert.")
        user.manager_id = manager.id

    def reset_microsoft_binding(self, user_id: uuid.UUID, admin: User) -> User:
        """Hebt die Bindung an die Microsoft-Kennung auf (z. B. Kontowechsel); der
        naechste Microsoft-Login bindet neu."""
        user = self.get(user_id)
        if user.ms_oid is not None:
            user.ms_oid = None
            self.audit_logs.create(
                {
                    "entity_type": "user",
                    "entity_id": user.id,
                    "action": "microsoft_oid_reset",
                    "changed_by": admin.email,
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
