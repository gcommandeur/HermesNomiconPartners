# NOMICON: Ansichten (Direct, Überlassung, Gesamt) - nur in der Nomicon-Kopie.
"""Eigene Ansichten (jeder Nutzer) und Freischaltung durch Admins."""

import uuid
from typing import cast

from fastapi import APIRouter
from sqlalchemy import select

from cc_crm.api.dependencies import AdminUser, CurrentUser, DatabaseSession
from cc_crm.core.errors import EntityNotFoundError
from cc_crm.models.user import User
from cc_crm.schemas.access_views import (
    MyViewsRead,
    SelectViewUpdate,
    UserViewsRead,
    UserViewsUpdate,
    ViewDefaultsRead,
    ViewDefaultsUpdate,
)
from cc_crm.services import access_views as service

router = APIRouter()


def _my_views(session: DatabaseSession, user: User) -> MyViewsRead:
    views = service.get_views(session, user)
    return MyViewsRead.model_validate(
        {"views": views, "default_view": service.get_default_view(session, user, views)}
    )


def _user_views(session: DatabaseSession, user: User) -> UserViewsRead:
    views = service.get_views(session, user)
    return UserViewsRead.model_validate(
        {
            "user_id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "is_active": user.is_active,
            "views": views,
            "default_view": service.get_default_view(session, user, views),
        }
    )


@router.get("/me/views", response_model=MyViewsRead)
def get_my_views(session: DatabaseSession, current_user: CurrentUser) -> MyViewsRead:
    return _my_views(session, current_user)


@router.put("/me/view", response_model=MyViewsRead)
def select_my_view(
    payload: SelectViewUpdate, session: DatabaseSession, current_user: CurrentUser
) -> MyViewsRead:
    """Merkt die gewählte Ansicht serverseitig (Startansicht beim nächsten Login)."""
    service.remember_view(session, current_user, payload.view)
    return _my_views(session, current_user)


@router.get("/admin/view-access", response_model=list[UserViewsRead])
def list_view_access(session: DatabaseSession, _admin: AdminUser) -> list[UserViewsRead]:
    users = session.scalars(select(User).order_by(User.display_name, User.email)).all()
    return [_user_views(session, user) for user in users]


@router.get("/admin/view-access/defaults", response_model=ViewDefaultsRead)
def get_view_defaults(session: DatabaseSession, _admin: AdminUser) -> ViewDefaultsRead:
    return ViewDefaultsRead.model_validate({"views": service.default_views(session)})


@router.put("/admin/view-access/defaults", response_model=ViewDefaultsRead)
def put_view_defaults(
    payload: ViewDefaultsUpdate, session: DatabaseSession, admin: AdminUser
) -> ViewDefaultsRead:
    saved = service.save_default_views(session, list(payload.views), admin)
    return ViewDefaultsRead.model_validate({"views": saved})


@router.get("/admin/users/{user_id}/views", response_model=UserViewsRead)
def get_user_views(
    user_id: uuid.UUID, session: DatabaseSession, _admin: AdminUser
) -> UserViewsRead:
    user = session.get(User, user_id)
    if user is None:
        raise EntityNotFoundError("Nutzer nicht gefunden")
    return _user_views(session, user)


@router.put("/admin/users/{user_id}/views", response_model=UserViewsRead)
def put_user_views(
    user_id: uuid.UUID,
    payload: UserViewsUpdate,
    session: DatabaseSession,
    admin: AdminUser,
) -> UserViewsRead:
    service.set_user_views(session, user_id, list(payload.views), payload.default_view, admin)
    user = cast(User, session.get(User, user_id))
    return _user_views(session, user)
