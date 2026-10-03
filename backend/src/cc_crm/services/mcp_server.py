"""Lesende Claude-Schnittstelle (MCP) - Skalierungs-Schritt 5b.

Ein schlanker MCP-Server ueber "Streamable HTTP" im JSON-Modus: ein POST pro
JSON-RPC-Nachricht, Antwort als application/json. Umgesetzt wird nur, was fuer
Werkzeuge noetig ist (`initialize`, `ping`, `tools/list`, `tools/call`). Bewusst
ohne das MCP-SDK: keine zusaetzliche Abhaengigkeit, kein Mount/Lifespan im
FastAPI-Prozess, und jedes Werkzeug laeuft direkt mit der Datenbank-Sitzung und
dem Nutzer der Anfrage - es gelten also GENAU dessen Rechte
(`process_owner_scope`, Freigaben).

Datenschutz: nur lesend, nur ueber API-Key eines Nutzers, ausgeschaltet solange
`CC_CRM_AI_ENABLED` nicht gesetzt ist (siehe api/v1/mcp.py). Kandidaten werden
OHNE Kontaktdaten (E-Mail, Telefon, LinkedIn) und ohne Gehaltsangaben
ausgegeben. Jeder Aufruf steht im Audit-Log (Aktion `mcp_tool_call`, nur Name
des Werkzeugs, keine Argumente/Ergebnisse) und zaehlt auf das Tageslimit.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cc_crm.core.config import get_settings
from cc_crm.core.errors import CcCrmError
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import TaskStatus
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.task import Task
from cc_crm.models.user import User
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.schemas.operational import CockpitRead
from cc_crm.services.candidates import CandidateService
from cc_crm.services.clients import ClientCompanyService
from cc_crm.services.operational import CockpitService
from cc_crm.services.submissions import CandidateSubmissionService

SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
AUDIT_ACTION = "mcp_tool_call"
MAX_LIMIT = 20


class McpError(Exception):
    """JSON-RPC-Fehler (Protokollebene, nicht Werkzeugfehler)."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[Session, User, dict[str, Any]], Any]


def _limit(arguments: dict[str, Any]) -> int:
    raw = arguments.get("limit", 10)
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise McpError(-32602, "limit muss eine ganze Zahl sein")
    return max(1, min(raw, MAX_LIMIT))


def _text(arguments: dict[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise McpError(-32602, f"{key} muss Text sein")
    return value[:200]


def _uuid(arguments: dict[str, Any], key: str) -> uuid.UUID:
    value = arguments.get(key)
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise McpError(-32602, f"{key} muss eine gueltige ID sein") from exc


def _scope(session: Session, user: User) -> tuple[list[uuid.UUID] | None, list[uuid.UUID]]:
    # Lokaler Import: api.dependencies importiert Services, nicht umgekehrt.
    from cc_crm.api.dependencies import process_owner_scope, shared_submission_ids

    return process_owner_scope(user, session), shared_submission_ids(user, session)


def _candidate_brief(candidate: Candidate) -> dict[str, Any]:
    """Ohne E-Mail, Telefon, LinkedIn, Gehalt, Kuendigungsfrist."""
    return {
        "id": str(candidate.id),
        "name": f"{candidate.first_name} {candidate.last_name}".strip(),
        "job_title": candidate.job_title,
        "qualification": candidate.qualification,
        "city": candidate.city,
        "postal_code": candidate.postal_code,
        "status": str(candidate.status),
        "cv_available": candidate.cv_available,
        "last_contact_at": candidate.last_contact_at.isoformat()
        if candidate.last_contact_at
        else None,
    }


def _search_candidates(session: Session, user: User, arguments: dict[str, Any]) -> Any:
    items, total = CandidateService(session).list_filtered(
        search=_text(arguments, "query"), role=_text(arguments, "role"), limit=_limit(arguments)
    )
    return {"total": total, "items": [_candidate_brief(item) for item in items]}


def _get_candidate(session: Session, user: User, arguments: dict[str, Any]) -> Any:
    candidate = CandidateService(session).get(_uuid(arguments, "candidate_id"))
    return {**_candidate_brief(candidate), "short_profile": candidate.short_profile}


def _search_clients(session: Session, user: User, arguments: dict[str, Any]) -> Any:
    items, total = ClientCompanyService(session).clients.filtered(
        search=_text(arguments, "query"), limit=_limit(arguments)
    )
    return {
        "total": total,
        "items": [
            {
                "id": str(item.id),
                "name": item.name,
                "city": item.city,
                "status": str(item.status),
                "kanzleigruppe": item.kanzleigruppe,
                "website": item.website,
            }
            for item in items
        ],
    }


def _get_client(session: Session, user: User, arguments: dict[str, Any]) -> Any:
    client_id = _uuid(arguments, "client_id")
    item = session.get(ClientCompany, client_id)
    if item is None:
        raise CcCrmError("Kanzlei nicht gefunden")
    return {
        "id": str(item.id),
        "name": item.name,
        "city": item.city,
        "postal_code": item.postal_code,
        "status": str(item.status),
        "kanzleigruppe": item.kanzleigruppe,
        "website": item.website,
    }


def _my_processes(session: Session, user: User, arguments: dict[str, Any]) -> Any:
    scope, shared = _scope(session, user)
    items, total = CandidateSubmissionService(session).submissions.filtered(
        owner_user_ids=scope, shared_submission_ids=shared, limit=_limit(arguments)
    )
    return {
        "total": total,
        "items": [
            {
                "id": str(item.id),
                "candidate_id": str(item.candidate_id),
                "client_company_id": str(item.client_company_id),
                "status": str(item.status),
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ],
    }


def _open_tasks(session: Session, user: User, arguments: dict[str, Any]) -> Any:
    rows = session.scalars(
        select(Task)
        .where(Task.owner_user_id == user.id, Task.status == TaskStatus.OPEN)
        .order_by(Task.due_at.is_(None), Task.due_at)
        .limit(_limit(arguments))
    ).all()
    return {
        "items": [
            {
                "id": str(task.id),
                "title": task.title,
                "due_at": task.due_at.isoformat() if task.due_at else None,
                "priority": str(task.priority),
            }
            for task in rows
        ]
    }


def _cockpit_summary(session: Session, user: User, arguments: dict[str, Any]) -> Any:
    scope, shared = _scope(session, user)
    cockpit = CockpitRead.model_validate(
        CockpitService(session).build("month", owner_user_ids=scope, shared_submission_ids=shared)
    )
    return {
        "period": cockpit.period,
        "kpis": cockpit.kpis.model_dump(mode="json"),
        "recruiting_kpis": cockpit.recruiting_kpis.model_dump(mode="json"),
    }


_LIMIT_SCHEMA = {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "default": 10}

TOOLS: tuple[Tool, ...] = (
    Tool(
        "search_candidates",
        "Kandidaten suchen (Name, Stichwort, Rolle). Liefert Kurzdaten OHNE Kontaktdaten.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "role": {"type": "string"},
                "limit": _LIMIT_SCHEMA,
            },
        },
        _search_candidates,
    ),
    Tool(
        "get_candidate",
        "Einen Kandidaten per ID oeffnen (Kurzprofil, ohne Kontaktdaten).",
        {
            "type": "object",
            "properties": {"candidate_id": {"type": "string"}},
            "required": ["candidate_id"],
        },
        _get_candidate,
    ),
    Tool(
        "search_clients",
        "Kanzleien suchen (Name, Website, Ort).",
        {"type": "object", "properties": {"query": {"type": "string"}, "limit": _LIMIT_SCHEMA}},
        _search_clients,
    ),
    Tool(
        "get_client",
        "Eine Kanzlei per ID oeffnen.",
        {
            "type": "object",
            "properties": {"client_id": {"type": "string"}},
            "required": ["client_id"],
        },
        _get_client,
    ),
    Tool(
        "list_my_processes",
        "Eigene (und geteilte bzw. Team-)Prozesse mit Status, nur sichtbare.",
        {"type": "object", "properties": {"limit": _LIMIT_SCHEMA}},
        _my_processes,
    ),
    Tool(
        "list_open_tasks",
        "Offene Aufgaben des Nutzers, faelligste zuerst.",
        {"type": "object", "properties": {"limit": _LIMIT_SCHEMA}},
        _open_tasks,
    ),
    Tool(
        "cockpit_summary",
        "Kennzahlen-Kurzfassung (Monat) fuer den Bereich des Nutzers.",
        {"type": "object", "properties": {}},
        _cockpit_summary,
    ),
)
_BY_NAME = {tool.name: tool for tool in TOOLS}


def _calls_today(session: Session, user: User) -> int:
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == AUDIT_ACTION,
                AuditLog.changed_by == user.email,
                AuditLog.changed_at >= midnight,
            )
        )
        or 0
    )


def _call_tool(session: Session, user: User, params: dict[str, Any]) -> dict[str, Any]:
    tool = _BY_NAME.get(str(params.get("name")))
    if tool is None:
        raise McpError(-32602, f"Unbekanntes Werkzeug: {params.get('name')}")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise McpError(-32602, "arguments muss ein Objekt sein")
    limit = get_settings().mcp_daily_limit
    if _calls_today(session, user) >= limit:
        return _tool_result({"fehler": f"Tageslimit von {limit} Aufrufen erreicht."}, error=True)
    # Zuerst protokollieren (zaehlt auch bei Fehlern), dann ausfuehren.
    AuditLogRepository(session).create(
        {
            "entity_type": "mcp_tool",
            "entity_id": user.id,
            "action": AUDIT_ACTION,
            "changed_by": user.email,
            "new_values": {"tool": tool.name},
        }
    )
    session.commit()
    try:
        return _tool_result(tool.handler(session, user, arguments))
    except CcCrmError as exc:
        return _tool_result({"fehler": str(exc)}, error=True)


def _tool_result(payload: Any, *, error: bool = False) -> dict[str, Any]:
    import json

    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "isError": error,
    }


def handle_message(session: Session, user: User, message: Any) -> dict[str, Any] | None:
    """Verarbeitet EINE JSON-RPC-Nachricht. None = Benachrichtigung (keine Antwort)."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, -32600, "Ungueltige Anfrage")
    request_id = message.get("id")
    method = message.get("method")
    if "id" not in message:  # Benachrichtigung, z.B. notifications/initialized
        return None
    params = message.get("params") or {}
    try:
        if method == "initialize":
            requested = params.get("protocolVersion") if isinstance(params, dict) else None
            version = requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
            result: dict[str, Any] = {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "hermes-crm", "version": "1.0"},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.input_schema,
                    }
                    for tool in TOOLS
                ]
            }
        elif method == "tools/call":
            if not isinstance(params, dict):
                raise McpError(-32602, "params muss ein Objekt sein")
            result = _call_tool(session, user, params)
        else:
            raise McpError(-32601, f"Methode nicht unterstuetzt: {method}")
    except McpError as exc:
        return _error(request_id, exc.code, exc.message)
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
