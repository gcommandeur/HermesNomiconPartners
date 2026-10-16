# NOMICON: Ansichten (Direct, Überlassung, Gesamt) - nur in der Nomicon-Kopie.
"""FastAPI-Abhaengigkeiten, die eine freigeschaltete Ansicht verlangen. 403 mit klarer Meldung
(kein Verstecken per 404). ID-Routen behalten ihr 404 für fremde Datensätze (Owner-Scope)."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.core.errors import PermissionDeniedError
from cc_crm.models.user import User
from cc_crm.services.access_views import (
    NOT_ALLOWED,
    VIEW_DIRECT,
    VIEW_MANAGEMENT,
    VIEW_STAFFING,
    has_view,
)


def require_view(view: str) -> Callable[..., User]:
    def dependency(session: DatabaseSession, current_user: CurrentUser) -> User:
        if not has_view(session, current_user, view):
            raise PermissionDeniedError(NOT_ALLOWED)
        return current_user

    dependency.__name__ = f"require_{view}_view"
    return dependency


require_direct_view = require_view(VIEW_DIRECT)
require_staffing_view = require_view(VIEW_STAFFING)
require_management_view = require_view(VIEW_MANAGEMENT)

DirectViewUser = Annotated[User, Depends(require_direct_view)]
StaffingViewUser = Annotated[User, Depends(require_staffing_view)]
ManagementViewUser = Annotated[User, Depends(require_management_view)]
