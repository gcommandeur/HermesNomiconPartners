# NOMICON: Ansichten (Direct, Überlassung, Gesamt) - nur in der Nomicon-Kopie.
"""Welche Ansichten ein Nutzer sehen darf, und wer sie vergeben darf.

Regeln (Server, nicht nur Oberflaeche):
- Admins haben immer alle drei Ansichten (nicht entziehbar).
- "management" (Gesamt) nur für Admins.
- Ein Nutzer ohne jede Freigabe-Zeile ("nie konfiguriert") bekommt den einstellbaren Standard
  (app_settings `views_default_for_new_users`, ohne Eintrag: nur "direct").
- Jede Änderung landet im Audit-Log (entity_type `user_view_access`)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.access_views import UserViewAccess, UserViewSettings
from cc_crm.models.app_setting import AppSetting
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.user import User

VIEW_DIRECT = "direct"
VIEW_STAFFING = "staffing"
VIEW_MANAGEMENT = "management"
ALL_VIEWS: tuple[str, ...] = (VIEW_DIRECT, VIEW_STAFFING, VIEW_MANAGEMENT)
VIEW_LABELS = {VIEW_DIRECT: "Direct", VIEW_STAFFING: "Überlassung", VIEW_MANAGEMENT: "Gesamt"}
DEFAULT_KEY = "views_default_for_new_users"
FALLBACK_DEFAULT: tuple[str, ...] = (VIEW_DIRECT,)
ENTITY_VIEW_ACCESS = "user_view_access"
NOT_ALLOWED = "Diese Ansicht ist für dein Konto nicht freigeschaltet."


def _ordered(views: set[str] | list[str]) -> list[str]:
    return [view for view in ALL_VIEWS if view in views]


def default_views(session: Session) -> list[str]:
    row = session.scalar(select(AppSetting).where(AppSetting.key == DEFAULT_KEY))
    raw = row.value if row is not None else None
    if isinstance(raw, list):
        cleaned = [v for v in raw if isinstance(v, str) and v in (VIEW_DIRECT, VIEW_STAFFING)]
        if cleaned:
            return _ordered(cleaned)
    return list(FALLBACK_DEFAULT)


def save_default_views(session: Session, views: list[str], actor: User) -> list[str]:
    _validate_views(views, target_is_admin=False)
    row = session.scalar(select(AppSetting).where(AppSetting.key == DEFAULT_KEY))
    ordered = _ordered(views)
    old = row.value if row is not None else list(FALLBACK_DEFAULT)
    if row is None:
        session.add(AppSetting(key=DEFAULT_KEY, value=ordered))
    else:
        row.value = ordered
    session.add(
        AuditLog(
            entity_type=ENTITY_VIEW_ACCESS,
            entity_id=actor.id,
            action="default_views_changed",
            changed_by=actor.email,
            old_values={"views": old},
            new_values={"views": ordered},
        )
    )
    session.commit()
    return ordered


def get_views(session: Session, user: User) -> list[str]:
    if user.is_admin:
        return list(ALL_VIEWS)
    rows = set(
        session.scalars(select(UserViewAccess.view).where(UserViewAccess.user_id == user.id)).all()
    )
    if not rows:
        return default_views(session)
    return _ordered(rows - {VIEW_MANAGEMENT})


def get_default_view(session: Session, user: User, views: list[str]) -> str:
    settings = session.scalar(select(UserViewSettings).where(UserViewSettings.user_id == user.id))
    if settings is not None and settings.default_view in views:
        return settings.default_view
    return VIEW_MANAGEMENT if user.is_admin and VIEW_MANAGEMENT in views else views[0]


def has_view(session: Session, user: User, view: str) -> bool:
    return view in get_views(session, user)


def _validate_views(views: list[str], *, target_is_admin: bool) -> None:
    unknown = [view for view in views if view not in ALL_VIEWS]
    if unknown:
        raise BusinessRuleError(f"Unbekannte Ansicht: {', '.join(unknown)}")
    if not views:
        raise BusinessRuleError("Mindestens eine Ansicht muss freigeschaltet bleiben.")
    if VIEW_MANAGEMENT in views and not target_is_admin:
        raise BusinessRuleError("Die Ansicht „Gesamt“ kann nur Admins freigeschaltet werden.")


def set_user_views(
    session: Session,
    target_id: uuid.UUID,
    views: list[str],
    default_view: str | None,
    actor: User,
) -> list[str]:
    """Setzt die Ansichten eines Nutzers (nur Admins rufen das auf). Gibt die neue Liste zurück."""
    target = session.get(User, target_id)
    if target is None:
        raise EntityNotFoundError("Nutzer nicht gefunden")
    wanted = set(views)
    # Admins behalten immer alle Ansichten - ein Entzug wird abgelehnt statt still ignoriert.
    if target.is_admin and wanted != set(ALL_VIEWS):
        raise BusinessRuleError("Admins behalten immer alle Ansichten (nicht entziehbar).")
    _validate_views(views, target_is_admin=target.is_admin)
    ordered = _ordered(wanted)
    if default_view is not None and default_view not in ordered:
        raise BusinessRuleError("Die Startansicht muss eine freigeschaltete Ansicht sein.")

    old_views = get_views(session, target)
    existing = {
        row.view: row
        for row in session.scalars(
            select(UserViewAccess).where(UserViewAccess.user_id == target.id)
        ).all()
    }
    for view, row in existing.items():
        if view not in wanted:
            session.delete(row)
    for view in ordered:
        if view not in existing:
            session.add(UserViewAccess(user_id=target.id, view=view, granted_by_user_id=actor.id))
    settings = session.scalar(select(UserViewSettings).where(UserViewSettings.user_id == target.id))
    old_default = settings.default_view if settings is not None else None
    if default_view is not None:
        if settings is None:
            session.add(UserViewSettings(user_id=target.id, default_view=default_view))
        else:
            settings.default_view = default_view
    if old_views != ordered or (default_view is not None and default_view != old_default):
        session.add(
            AuditLog(
                entity_type=ENTITY_VIEW_ACCESS,
                entity_id=target.id,
                action="views_changed",
                changed_by=actor.email,
                old_values={"views": old_views, "default_view": old_default},
                new_values={"views": ordered, "default_view": default_view or old_default},
            )
        )
    session.commit()
    return ordered


def remember_view(session: Session, user: User, view: str) -> None:
    """Merkt die zuletzt gewählte Ansicht (Umschalter im Kopf)."""
    if view not in get_views(session, user):
        raise BusinessRuleError(NOT_ALLOWED)
    settings = session.scalar(select(UserViewSettings).where(UserViewSettings.user_id == user.id))
    if settings is None:
        session.add(UserViewSettings(user_id=user.id, default_view=view))
    else:
        settings.default_view = view
    session.commit()
