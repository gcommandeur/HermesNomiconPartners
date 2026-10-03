from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, HTTPException, Response, status

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.core.config import get_settings
from cc_crm.services.mcp_server import handle_message

router = APIRouter(prefix="/mcp")


@router.post("")
def mcp_endpoint(
    session: DatabaseSession,
    current_user: CurrentUser,
    message: Annotated[Any, Body()],
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> Any:
    """MCP (Streamable HTTP, JSON-Modus) - lesender Zugriff fuer Claude.

    Nur mit API-Key (X-API-Key), nicht mit einer Browser-Sitzung; es gelten die
    Rechte des Key-Besitzers. Ausgeschaltet (404), solange CC_CRM_AI_ENABLED
    nicht gesetzt ist. Details: services/mcp_server.py."""
    if not get_settings().ai_enabled or api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if isinstance(message, list):
        # JSON-RPC-Batches sind in der MCP-Fassung 2025-06-18 nicht vorgesehen.
        return Response(
            content='{"jsonrpc":"2.0","id":null,"error":{"code":-32600,"message":"Keine Batches"}}',
            media_type="application/json",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    response = handle_message(session, current_user, message)
    if response is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    return response
