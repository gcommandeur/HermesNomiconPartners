"""OAuth-Endpunkte, mit denen sich Claude (Team-Konto) an Hermes anmeldet.

Oeffentlich (ohne Hermes-Login) sind nur Metadaten, Registrierung, /authorize
(leitet zur Zustimmungsseite) und /token. Die Zustimmung selbst und die
Verbindungsverwaltung brauchen den normalen Hermes-Login. Alles ist ausgeschaltet
(404), solange CC_CRM_AI_ENABLED nicht gesetzt ist."""

import uuid
from datetime import datetime
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Body, Form, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.core.config import get_settings
from cc_crm.services.oauth_provider import (
    SCOPE,
    OAuthError,
    OAuthProvider,
    frontend_origin,
    public_base_url,
)

public_router = APIRouter(prefix="/oauth")
router = APIRouter(prefix="/oauth")


def _require_enabled() -> None:
    if not get_settings().ai_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _error_response(exc: OAuthError) -> JSONResponse:
    body = {"error": exc.error}
    if exc.description:
        body["error_description"] = exc.description
    return JSONResponse(
        body,
        status_code=exc.status_code,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


# --- Metadaten ---------------------------------------------------------------


@public_router.get("/protected-resource")
def protected_resource_metadata() -> dict[str, Any]:
    """RFC 9728 - ueber `resource_metadata` im 401 von /mcp referenziert."""
    _require_enabled()
    base = public_base_url()
    return {
        "resource": f"{base}/mcp",
        "authorization_servers": [f"{base}/oauth"],
        "bearer_methods_supported": ["header"],
        "scopes_supported": [SCOPE],
    }


def _authorization_server_metadata() -> dict[str, Any]:
    base = public_base_url()
    issuer = f"{base}/oauth"
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "registration_endpoint": f"{issuer}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": [SCOPE],
        # Pflichtfelder der OpenID-Discovery (hier ohne ID-Token genutzt):
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }


@public_router.get("/.well-known/openid-configuration")
def openid_configuration() -> dict[str, Any]:
    _require_enabled()
    return _authorization_server_metadata()


@public_router.get("/.well-known/oauth-authorization-server")
def authorization_server_metadata() -> dict[str, Any]:
    _require_enabled()
    return _authorization_server_metadata()


# --- Registrierung, Anmeldung, Token -------------------------------------------


@public_router.post("/register", status_code=status.HTTP_201_CREATED)
def register_client(session: DatabaseSession, metadata: Annotated[Any, Body()]) -> JSONResponse:
    _require_enabled()
    if not isinstance(metadata, dict):
        return _error_response(OAuthError("invalid_client_metadata", "JSON-Objekt erwartet"))
    try:
        client = OAuthProvider(session).register_client(metadata)
    except OAuthError as exc:
        return _error_response(exc)
    return JSONResponse(
        {
            "client_id": client.client_id,
            "client_name": client.client_name,
            "redirect_uris": client.redirect_uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
        status_code=status.HTTP_201_CREATED,
        headers={"Cache-Control": "no-store"},
    )


@public_router.get("/authorize", include_in_schema=False)
def authorize(
    session: DatabaseSession,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    response_type: str = "code",
    code_challenge_method: str = "S256",
    state: str | None = None,
    scope: str | None = None,
) -> Any:
    """Startet die Anmeldung: prueft die Anfrage und leitet den Browser zur
    Zustimmungsseite im Hermes-Frontend (dort Hermes-Login falls noetig)."""
    _require_enabled()
    if response_type != "code":
        raise HTTPException(status_code=400, detail="response_type muss 'code' sein")
    try:
        request = OAuthProvider(session).begin_authorization(
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            state=state,
            scope=scope,
        )
    except OAuthError as exc:
        # Vor einer geprueften redirect_uri nie dorthin weiterleiten.
        raise HTTPException(status_code=400, detail=exc.description or exc.error) from exc
    query = urlencode({"request": str(request.id)})
    return RedirectResponse(f"{frontend_origin()}/oauth/zustimmung?{query}")


@public_router.post("/token")
def token(
    session: DatabaseSession,
    grant_type: Annotated[str, Form()],
    client_id: Annotated[str, Form()],
    code: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    code_verifier: Annotated[str | None, Form()] = None,
    refresh_token: Annotated[str | None, Form()] = None,
) -> JSONResponse:
    _require_enabled()
    provider = OAuthProvider(session)
    try:
        if grant_type == "authorization_code":
            if not (code and redirect_uri and code_verifier):
                raise OAuthError("invalid_request", "code, redirect_uri und code_verifier fehlen")
            result = provider.exchange_code(
                client_id=client_id,
                code=code,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        elif grant_type == "refresh_token":
            if not refresh_token:
                raise OAuthError("invalid_request", "refresh_token fehlt")
            result = provider.refresh(client_id=client_id, refresh_token=refresh_token)
        else:
            raise OAuthError("unsupported_grant_type", grant_type[:40])
    except OAuthError as exc:
        return _error_response(exc)
    return JSONResponse(result, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


# --- Zustimmung und Verbindungen (normaler Hermes-Login) ----------------------


class ConsentInfo(BaseModel):
    client_name: str
    redirect_host: str
    scope: str
    user_email: str


class ConsentDecision(BaseModel):
    request_id: uuid.UUID
    approve: bool


class ConsentResult(BaseModel):
    redirect_url: str


class OAuthConnection(BaseModel):
    id: uuid.UUID
    client_name: str
    created_at: datetime
    last_used_at: datetime | None = None


@router.get("/consent/{request_id}", response_model=ConsentInfo)
def consent_info(
    request_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> ConsentInfo:
    _require_enabled()
    info = OAuthProvider(session).consent_info(request_id)
    return ConsentInfo(**info, user_email=current_user.email)


@router.post("/consent", response_model=ConsentResult)
def decide_consent(
    payload: ConsentDecision, session: DatabaseSession, current_user: CurrentUser
) -> ConsentResult:
    _require_enabled()
    url = OAuthProvider(session).decide(current_user, payload.request_id, payload.approve)
    return ConsentResult(redirect_url=url)


@router.get("/connections", response_model=list[OAuthConnection])
def list_connections(session: DatabaseSession, current_user: CurrentUser) -> list[OAuthConnection]:
    return [
        OAuthConnection(
            id=token.id,
            client_name=name,
            created_at=token.created_at,
            last_used_at=token.last_used_at,
        )
        for token, name in OAuthProvider(session).connections(current_user)
    ]


@router.delete("/connections/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_connection(
    token_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> None:
    OAuthProvider(session).revoke(current_user, token_id)
