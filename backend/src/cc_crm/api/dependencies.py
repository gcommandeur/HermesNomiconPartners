import uuid
from typing import Annotated, Any, cast

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from cc_crm.core.errors import AuthenticationError, EntityNotFoundError, PermissionDeniedError
from cc_crm.infrastructure.database.session import get_db_session
from cc_crm.models.recruiting import Fee, Placement
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.submission_share import SubmissionShare
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


def process_owner_scope(current_user: User, session: Session) -> list[uuid.UUID] | None:
    """Sichtbarkeitsgrenze fuer laufende Prozesse und alles, was daran haengt
    (Interviews, Offers, Placements, Feedback, Fees). Ergebnis:
    - None: keine Einschraenkung (Admin),
    - Liste von Nutzer-IDs, deren Prozesse sichtbar sind: Mitarbeiter nur die
      eigene ID, Teamleiter die eigene plus die seiner direkten Mitarbeiter
      (users.manager_id), jeweils LIVE aus der DB - eine geaenderte Zuordnung
      wirkt sofort, ohne Cache.
    Immer eine Liste statt einer Einzel-UUID, damit alle Aufrufer genau einen
    Fall behandeln (`in` bzw. `.in_()`). Bewusst NICHT fuer Kandidaten/
    Kanzleien - die sind der gemeinsame Pool der Agentur."""
    if current_user.is_admin:
        return None
    if current_user.is_team_lead:
        reports = session.scalars(select(User.id).where(User.manager_id == current_user.id)).all()
        return [current_user.id, *reports]
    return [current_user.id]


def shared_submission_ids(current_user: User, session: Session) -> list[uuid.UUID]:
    """IDs der Prozesse, die per Freigabe (submission_shares) mit dem Nutzer
    geteilt wurden - LIVE aus der DB, ein Widerruf wirkt sofort. Ergaenzt
    process_owner_scope ADDITIV (die Rueckgabe dort bleibt unveraendert, siehe
    dessen Signatur): Listen-Endpunkte verknuepfen beide mit OR
    (`owner in scope OR id in shared`). Fuer Admins leer - sie sehen ohnehin
    alles (scope is None)."""
    if current_user.is_admin:
        return []
    return list(
        session.scalars(
            select(SubmissionShare.submission_id).where(
                SubmissionShare.shared_with_user_id == current_user.id
            )
        ).all()
    )


def user_can_access_submission(
    session: Session, current_user: User, submission_id: uuid.UUID
) -> bool:
    """Admin, Eigentuemer/Teamleiter ueber den Scope ODER per Freigabe. Ein
    nicht existierender Prozess ist fuer Nicht-Admins nie zugaenglich."""
    scope = process_owner_scope(current_user, session)
    if scope is None:
        return True
    owner_user_id = session.scalar(
        select(CandidateSubmission.owner_user_id).where(CandidateSubmission.id == submission_id)
    )
    if owner_user_id in scope:
        return True
    return _has_share(session, current_user, submission_id)


def user_can_manage_shares(
    session: Session, current_user: User, submission_id: uuid.UUID
) -> bool:
    """Freigaben anlegen/entziehen: nur Admin, Eigentuemer oder dessen
    Teamleiter - also wer den Prozess ueber process_owner_scope erreicht, NICHT
    wer ihn nur per Freigabe sieht (sonst koennte ein Empfaenger den Prozess an
    beliebige Dritte weitergeben)."""
    scope = process_owner_scope(current_user, session)
    if scope is None:
        return True
    owner_user_id = session.scalar(
        select(CandidateSubmission.owner_user_id).where(CandidateSubmission.id == submission_id)
    )
    return owner_user_id in scope


def _has_share(session: Session, current_user: User, submission_id: uuid.UUID) -> bool:
    return (
        session.scalar(
            select(SubmissionShare.id).where(
                SubmissionShare.shared_with_user_id == current_user.id,
                SubmissionShare.submission_id == submission_id,
            )
        )
        is not None
    )


def require_submission_access(
    submission_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> None:
    """Eigentuemer-Pruefung fuer JEDEN Endpunkt mit submission_id im Pfad
    (api/v1/submissions.py, inkl. der verschachtelten Interview-/Offer-/
    Feedback-/Placement-Routen - die Dependency laeuft vor dem Handler, das
    Kind-Objekt wird also nie angefasst, bevor der Prozess geprueft ist).
    Ergaenzt process_owner_scope, das nur die Listen-Endpunkte abdeckt.

    Zugriff haben Admins, der Scope (Eigentuemer/Teamleiter) und Personen, mit
    denen der Prozess geteilt wurde (SubmissionShare). Nicht-Admins sonst: 404
    mit derselben Meldung wie bei einer nicht existierenden ID - 403 wuerde die
    Existenz verraten. Admins und ein nicht existierender Prozess laufen
    unveraendert an den Handler durch (der meldet das 404 selbst)."""
    if not user_can_access_submission(session, current_user, submission_id):
        raise EntityNotFoundError("CandidateSubmission not found")


SubmissionAccess = Depends(require_submission_access)


def _submission_of_placement(placement_id: uuid.UUID) -> Select[Any]:
    return cast(
        "Select[Any]",
        select(CandidateSubmission.id, CandidateSubmission.owner_user_id)
        .join(Placement, Placement.submission_id == CandidateSubmission.id)
        .where(Placement.id == placement_id),
    )


def _submission_of_fee(fee_id: uuid.UUID) -> Select[Any]:
    # Fee.placement_id -> Placement.submission_id -> CandidateSubmission
    return cast(
        "Select[Any]",
        select(CandidateSubmission.id, CandidateSubmission.owner_user_id)
        .join(Placement, Placement.submission_id == CandidateSubmission.id)
        .join(Fee, Fee.placement_id == Placement.id)
        .where(Fee.id == fee_id),
    )


def _is_visible(session: Session, current_user: User, submission_statement: Select[Any]) -> bool:
    """`submission_statement` liefert (submission_id, owner_user_id) des
    Prozesses, zu dem das Objekt gehoert (oder keine Zeile)."""
    scope = process_owner_scope(current_user, session)
    if scope is None:
        return True
    row = session.execute(submission_statement).first()
    if row is None:
        return False
    submission_id: uuid.UUID = row[0]
    owner_user_id: uuid.UUID | None = row[1]
    if owner_user_id in scope:
        return True
    return _has_share(session, current_user, submission_id)


def user_owns_fee(session: Session, current_user: User, fee_id: uuid.UUID) -> bool:
    """Admin, Eigentuemer/Team oder per Freigabe: Zugriff auf den Prozess, zu dem
    die Rechnung gehoert."""
    return _is_visible(session, current_user, _submission_of_fee(fee_id))


def require_placement_access(
    placement_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> None:
    """Wie require_submission_access, fuer Routen mit placement_id im Pfad
    (Rechnungen eines Placements). Fremd und nicht existent: dasselbe 404."""
    if not _is_visible(session, current_user, _submission_of_placement(placement_id)):
        raise EntityNotFoundError("Placement not found")


def require_fee_access(
    fee_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> None:
    """Wie require_submission_access, fuer Routen mit fee_id im Pfad."""
    if not user_owns_fee(session, current_user, fee_id):
        raise EntityNotFoundError("Rechnung nicht gefunden")


PlacementAccess = Depends(require_placement_access)
FeeAccess = Depends(require_fee_access)
