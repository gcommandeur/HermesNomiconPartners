# API Keys für Agenten und Integrationen

Menschliche Logins (`/api/v1/auth/login`) laufen 24 Stunden und sind an eine Person gebunden.
Seit 2026-09-24 verlangt der interaktive Login zusaetzlich einen per E-Mail verschickten
6-stelligen Code (2FA, siehe `services/auth.py`) - API-Keys sind davon **nicht** betroffen:
`POST /auth/login`, `/login/verify`, `/login/resend` existieren fuer den API-Key-Pfad gar nicht,
`X-API-Key` authentifiziert weiterhin in einem einzigen Request ueber `ApiKeyService`.
Für Bots, Agenten und Integrationen (Bullhorn-Sync, kuenftige AI-Matching-Agenten, Webhooks)
gibt es stattdessen langlebige API-Keys, die als eigener Service-Account authentifizieren.

## Key anlegen

```powershell
cd backend
python scripts/create_api_key.py "Bullhorn Sync"
```

Gibt einmalig den Rohschluessel aus (`ccrm_...`). Bitte sicher speichern - er ist danach nicht
mehr abrufbar (nur der Hash liegt in der Datenbank).

Optional mit Ablaufdatum (z.B. fuer einen zeitlich begrenzten Export-Job):

```powershell
python scripts/create_api_key.py "Temporary Export Job" --expires-in-days 30
```

Ohne `--expires-in-days` laeuft der Key nie ab (unveraendertes Verhalten).

## Verwendung

Statt `Authorization: Bearer <token>` einfach den Header `X-API-Key: <key>` setzen:

```powershell
curl http://127.0.0.1:8000/api/v1/candidates -H "X-API-Key: ccrm_..."
```

Beide Auth-Wege laufen ueber dieselbe `get_current_user`-Dependency, jeder Request landet also mit
demselben Rechte- und Datenmodell wie ein menschlicher Nutzer - inklusive Activities/AuditLogs, die
den Service-Account als `changed_by`/Owner zeigen.

## Widerruf

Ueber Python-Shell oder ein kleines Skript:

```python
from cc_crm.infrastructure.database.session import SessionLocal
from cc_crm.services.api_keys import ApiKeyService
with SessionLocal() as session:
    ApiKeyService(session).revoke(api_key_id)
```

Ein widerrufener Key wird sofort mit 401 abgelehnt (siehe `tests/api/test_api_keys.py`). Ein
abgelaufener Key (`expires_at` in der Vergangenheit) wird bei der naechsten Auth-Pruefung genauso
wie ein widerrufener Key behandelt.

## Lesende Claude-Schnittstelle (MCP)

Unter `POST /api/v1/mcp` gibt es einen lesenden MCP-Server (Streamable HTTP, JSON-Modus). Er ist **standardmäßig aus** (404) und wird erst mit der Variable `CC_CRM_AI_ENABLED=true` eingeschaltet - das erst tun, wenn die Auftragsverarbeitung mit Anthropic geklärt ist.

- **Schlüssel anlegen** (nur der Nutzer, am Laptop, gegen die gewünschte Datenbank):
  `python scripts/create_api_key.py "Claude Lukas" --mcp-for-user lukas@firma.de [--expires-in-days 90]`.
  Der Schlüssel ist an diesen echten Nutzer gebunden (dessen Rechte: Mitarbeiter, Teamleiter, Admin) und gilt **nur** für `/api/v1/mcp` - auf jeder anderen Route gibt er 401. Er wird nur einmal angezeigt.
- **Werkzeuge (nur lesend):** `search_candidates`, `get_candidate`, `search_clients`, `get_client`, `list_my_processes`, `list_open_tasks`, `cockpit_summary`. Kandidaten kommen ohne E-Mail, Telefon, LinkedIn und Gehaltsangaben.
- **Audit und Limit:** jeder Aufruf steht im Audit-Log (`mcp_tool_call`, nur der Werkzeugname), Tageslimit pro Nutzer über `CC_CRM_MCP_DAILY_LIMIT` (Standard 500).
- **Einbinden** z.B. in Claude Code: `claude mcp add --transport http hermes https://<host>/api/v1/mcp --header "X-API-Key: <schlüssel>"`.
