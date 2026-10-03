import uuid

from fastapi import APIRouter

from cc_crm.api.dependencies import AdminUser, CurrentUser, DatabaseSession, process_owner_scope
from cc_crm.models.user import User
from cc_crm.schemas.user import (
    CalendarFeedTokenRead,
    UserAdminRead,
    UserAdminUpdate,
    UserBriefRead,
)
from cc_crm.services.users import UserService

router = APIRouter(prefix="/users")


def _admin_read(user: User, labels: dict[uuid.UUID, str]) -> UserAdminRead:
    return UserAdminRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        role=user.role,
        manager_id=user.manager_id,
        manager_name=labels.get(user.manager_id) if user.manager_id else None,
    )


@router.get("", response_model=list[UserAdminRead])
def list_users(session: DatabaseSession, _admin: AdminUser) -> list[UserAdminRead]:
    users = UserService(session).list_all()
    labels = {user.id: user.display_name or user.email for user in users}
    return [_admin_read(user, labels) for user in users]


@router.get("/assignable", response_model=list[UserBriefRead])
def list_assignable_users(
    session: DatabaseSession, _current_user: CurrentUser
) -> list[UserBriefRead]:
    """Fuer JEDEN eingeloggten Nutzer zugaenglich (anders als GET /users,
    admin-only) - Grundlage fuer die Owner-Auswahl (owner_user_id) beim
    Anlegen von Kandidat/Kanzlei/Prozess/Aufgabe, siehe schemas/user.py::
    UserBriefRead."""
    users = UserService(session).list_all()
    return [
        UserBriefRead(id=user.id, email=user.email, display_name=user.display_name)
        for user in users
    ]


@router.get("/scope", response_model=list[UserBriefRead])
def list_scope_users(session: DatabaseSession, current_user: CurrentUser) -> list[UserBriefRead]:
    """Nutzer im eigenen Sichtbereich (process_owner_scope): Admin alle,
    Teamleiter sie selbst + Team, Mitarbeiter nur sie selbst. Grundlage fuer
    Nutzerfilter in Analytics und Kalender - dort duerfen nur diese gewaehlt
    werden (der Server ignoriert andere ohnehin)."""
    scope = process_owner_scope(current_user, session)
    users = UserService(session).list_all()
    return [
        UserBriefRead(id=user.id, email=user.email, display_name=user.display_name)
        for user in users
        if scope is None or user.id in scope
    ]


@router.patch("/{user_id}", response_model=UserAdminRead)
def update_user(
    user_id: uuid.UUID,
    payload: UserAdminUpdate,
    session: DatabaseSession,
    admin: AdminUser,
) -> UserAdminRead:
    service = UserService(session)
    user = service.update_admin_fields(user_id, payload, admin)
    labels = {item.id: item.display_name or item.email for item in service.list_all()}
    return _admin_read(user, labels)


@router.post("/{user_id}/rotate-calendar-feed-token", response_model=CalendarFeedTokenRead)
def rotate_calendar_feed_token(
    user_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> CalendarFeedTokenRead:
    # Owner ODER Admin - anders als die reinen Admin-Endpunkte oben deshalb
    # kein require_admin; die Berechtigungspruefung (Owner oder Admin) sitzt
    # im Service (UserService.rotate_calendar_feed_token).
    user = UserService(session).rotate_calendar_feed_token(user_id, current_user)
    return CalendarFeedTokenRead(calendar_feed_token=user.calendar_feed_token)
