# Bullhorn- und LinkedIn-Import

## Bullhorn (echte REST-API-Anbindung)

Bullhorn bietet eine dokumentierte REST-API mit OAuth2-Login. Der Adapter liegt unter
`backend/src/cc_crm/integrations/bullhorn/`.

1. In Bullhorn ein API-Center-Credential anlegen (Client ID/Secret) und einen API-Benutzer
   (Username/Password) einrichten.
2. In `backend/.env` ergaenzen:
   ```
   BULLHORN_CLIENT_ID=...
   BULLHORN_CLIENT_SECRET=...
   BULLHORN_USERNAME=...
   BULLHORN_PASSWORD=...
   ```
3. Dry-Run (zeigt nur an, was importiert wuerde, schreibt nichts):
   ```powershell
   python scripts/sync_bullhorn.py candidates
   python scripts/sync_bullhorn.py clients
   ```
4. Tatsaechlicher Import erst nach Pruefung, explizit mit `--commit`:
   ```powershell
   python scripts/sync_bullhorn.py candidates --commit --limit 500
   python scripts/sync_bullhorn.py clients --commit --limit 500
   ```

Duplikate werden ueber die bestehenden Unique-Constraints (E-Mail/Kandidatennummer bei
Kandidaten, Name bei Kanzleien) automatisch uebersprungen und gezaehlt.

**Wichtig:** Dieser Adapter folgt dem offiziell dokumentierten Bullhorn-Auth-Flow, wurde in
dieser Umgebung aber nicht gegen einen echten Bullhorn-Tenant getestet (keine Zugangsdaten
vorhanden). Bitte zuerst mit einem kleinen `--limit` und gegen eine Sandbox/Testmandant
verifizieren, bevor grosse Datenmengen gezogen werden.

## LinkedIn (kein Scraping, sondern legitimer Datenexport)

LinkedIn stellt keine allgemeine API bereit, mit der ein normaler Account Kontakte/Kandidaten
programmatisch abrufen kann - die entsprechenden Enterprise-APIs (Recruiter System Connect,
Talent Solutions) erfordern einen eigenen Partnervertrag mit LinkedIn. Automatisiertes
Auslesen der Webseite verstoesst gegen die LinkedIn-Nutzungsbedingungen und wird hier bewusst
nicht implementiert.

Der unterstuetzte, regelkonforme Weg:

1. In LinkedIn: **Einstellungen & Datenschutz -> Datenschutz -> Kopie deiner Daten anfordern
   -> Verbindungen** (oder ein CSV-Export aus Sales Navigator/Recruiter) herunterladen.
2. Datei konvertieren:
   ```powershell
   python scripts/convert_linkedin_export.py Connections.csv candidates_ready.csv
   ```
3. `candidates_ready.csv` ueber den bestehenden Import hochladen (Import-Assistent im
   Frontend oder direkt `POST /api/v1/import/candidates/preview` gefolgt von
   `/commit`) - inklusive Fehlerliste, Duplikatpruefung und expliziter Bestaetigung vor dem
   Schreiben, genau wie beim normalen CSV/XLSX-Import.
