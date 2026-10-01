import uuid
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from cc_crm.core.errors import AuthenticationError, PermissionDeniedError
from cc_crm.infrastructure.database.session import get_db_session
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
