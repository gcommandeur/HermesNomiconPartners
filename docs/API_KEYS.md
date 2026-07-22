# API Keys für Agenten und Integrationen

Menschliche Logins (`/api/v1/auth/login`) laufen 14 Tage und sind an eine Person gebunden.
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
