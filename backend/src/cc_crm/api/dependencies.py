import uuid
from typing import Annotated, Any

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from cc_crm.core.errors import AuthenticationError, EntityNotFoundError, PermissionDeniedError
from cc_crm.infrastructure.database.session import get_db_session
from cc_crm.models.recruiting import Fee, Placement
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.user import User
from cc_crm.services.api_keys import ApiKeyService
from cc_crm.services.auth import AuthService

DatabaseSession = Annotated[Session, Depends(get_db_session)]

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    session: DatabaseSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> User:
    """Accepts either a human login session (Bearer token) or a long-lived
    API key (X-API-Key header) for agents/integrations - see
    docs/API_KEYS.md.
    """
    if api_key is not None:
        return ApiKeyService(session).user_for_key(api_key)
    if credentials is None:
        raise AuthenticationError("Missing bearer token or X-API-Key header")
    return AuthService(session).user_for_token(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(current_user: CurrentUser) -> User:
    """Fuer Endpunkte, die nur fuer Admins gedacht sind (Nutzerverwaltung,
    siehe api/v1/users.py) - 403 statt 401, da der Nutzer durchaus
    authentifiziert ist, nur eben nicht berechtigt."""
    if not current_user.is_admin:
        raise PermissionDeniedError("Nur fuer Admins zugaenglich.")
    return current_user


AdminUser = Annotated[User, Depends(require_admin)]


def process_owner_scope(current_user: User) -> uuid.UUID | None:
    """Sichtbarkeitsgrenze fuer laufende Prozesse und alles, was daran haengt
    (Interviews, Offers, Placements, Feedback, Fees): Nicht-Admins sehen nur
    eigene, Admins alles (None = keine Einschraenkung). Bewusst NICHT fuer
    Kandidaten/Kanzleien - die sind der gemeinsame Pool der Agentur."""
    return None if current_user.is_admin else current_user.id


def require_submission_access(
    submission_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> None:
    """Eigentuemer-Pruefung fuer JEDEN Endpunkt mit submission_id im Pfad
    (api/v1/submissions.py, inkl. der verschachtelten Interview-/Offer-/
    Feedback-/Placement-Routen - die Dependency laeuft vor dem Handler, das
    Kind-Objekt wird also nie angefasst, bevor der Prozess geprueft ist).
    Ergaenzt process_owner_scope, das nur die Listen-Endpunkte abdeckt.

    Nicht-Admins auf einen fremden Prozess: 404 mit derselben Meldung wie bei
    einer nicht existierenden ID - 403 wuerde die Existenz verraten. Admins
    und ein nicht existierender Prozess laufen unveraendert an den Handler
    durch (der meldet das 404 selbst)."""
    scope = process_owner_scope(current_user)
    if scope is None:
        return
    owner_user_id = session.scalar(
        select(CandidateSubmission.owner_user_id).where(CandidateSubmission.id == submission_id)
    )
    if owner_user_id != scope:
        raise EntityNotFoundError("CandidateSubmission not found")


SubmissionAccess = Depends(require_submission_access)


def _owner_of_placement(placement_id: uuid.UUID) -> Select[Any]:
    return (
        select(CandidateSubmission.owner_user_id)
        .join(Placement, Placement.submission_id == CandidateSubmission.id)
        .where(Placement.id == placement_id)
    )


def _owner_of_fee(fee_id: uuid.UUID) -> Select[Any]:
    # Fee.placement_id -> Placement.submission_id -> CandidateSubmission.owner_user_id
    return (
        select(CandidateSubmission.owner_user_id)
        .join(Placement, Placement.submission_id == CandidateSubmission.id)
        .join(Fee, Fee.placement_id == Placement.id)
        .where(Fee.id == fee_id)
    )


def _is_visible(
    session: Session, current_user: User, owner_statement: Select[Any]
) -> bool:
    scope = process_owner_scope(current_user)
    if scope is None:
        return True
    return bool(session.scalar(owner_statement) == scope)


def user_owns_fee(session: Session, current_user: User, fee_id: uuid.UUID) -> bool:
    """Admin oder Eigentuemer des Prozesses, zu dem die Rechnung gehoert."""
    return _is_visible(session, current_user, _owner_of_fee(fee_id))


def require_placement_access(
    placement_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> None:
    """Wie require_submission_access, fuer Routen mit placement_id im Pfad
    (Rechnungen eines Placements). Fremd und nicht existent: dasselbe 404."""
    if not _is_visible(session, current_user, _owner_of_placement(placement_id)):
        raise EntityNotFoundError("Placement not found")


def require_fee_access(
    fee_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> None:
    """Wie require_submission_access, fuer Routen mit fee_id im Pfad."""
    if not user_owns_fee(session, current_user, fee_id):
        raise EntityNotFoundError("Rechnung nicht gefunden")


PlacementAccess = Depends(require_placement_access)
FeeAccess = Depends(require_fee_access)
