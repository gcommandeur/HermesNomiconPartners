from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.core.config import get_settings
from cc_crm.core.observability import set_request_user
from cc_crm.models.user import User
from cc_crm.services.api_keys import ApiKeyService
from cc_crm.services.mcp_server import handle_message
from cc_crm.services.oauth_provider import OAuthProvider, public_base_url

router = APIRouter(prefix="/mcp")


def _unauthorized() -> JSONResponse:
    """401 mit Verweis auf die Metadaten - damit startet Claude die Anmeldung
    (Claude wertet den Hinweis nur bei einem 401 aus, nicht bei 200)."""
    return JSONResponse(
        {"detail": "Anmeldung erforderlich"},
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers={
            "WWW-Authenticate": (
                f'Bearer resource_metadata="{public_base_url()}/oauth/protected-resource"'
            )
        },
    )


@router.post("")
def mcp_endpoint(
    session: DatabaseSession,
    message: Annotated[Any, Body()],
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Any:
    """MCP (Streamable HTTP, JSON-Modus) - Zugriff fuer Claude.

    Zwei Wege, beide gebunden an einen Hermes-Nutzer (es gelten genau dessen
    Rechte): ein API-Key (X-API-Key) oder ein OAuth-Token, das Claude ueber die
    Anmeldung bei Hermes erhalten hat (Authorization: Bearer ..., siehe
    services/oauth_provider.py). Eine Browser-Sitzung gilt hier nicht. Lesend,
    dazu Vorschlaege mit Freigabe-Pflicht. Ausgeschaltet (404), solange
    CC_CRM_AI_ENABLED nicht gesetzt ist. Details: services/mcp_server.py."""
    if not get_settings().ai_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    user: User | None = None
    if api_key is not None:
        user = ApiKeyService(session).authenticate(api_key)[0]
    elif authorization and authorization.lower().startswith("bearer "):
        user = OAuthProvider(session).user_for_access_token(authorization[7:].strip())
    if user is None:
        return _unauthorized()
    set_request_user(str(user.id))
    if isinstance(message, list):
        # JSON-RPC-Batches sind in der MCP-Fassung 2025-06-18 nicht vorgesehen.
        return Response(
            content='{"jsonrpc":"2.0","id":null,"error":{"code":-32600,"message":"Keine Batches"}}',
            media_type="application/json",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    response = handle_message(session, user, message)
    if response is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    return response
