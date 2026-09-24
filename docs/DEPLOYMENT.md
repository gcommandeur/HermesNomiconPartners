# Hermes CRM – Deployment-Anleitung

Diese Anleitung beschreibt das tatsächliche Produktiv-Setup von Hermes CRM.
Stand: 2026-07-20. Alles läuft in einem einzigen DigitalOcean-Konto/Team
("My Team"), Region Frankfurt (FRA1).

## Übersicht

| Komponente | Dienst | Name / Ort |
|---|---|---|
| Backend (FastAPI) | App Platform Web Service | App `hermescrm`, Komponente `hermescrm` |
| Frontend (Next.js) | App Platform Web Service | App `hermescrm`, Komponente `hermescrm-frontend` |
| Datenbank | Managed PostgreSQL | Cluster `db-pgsql-fra1-22616` |
| Dokumentenspeicher (CVs, Verträge) | Spaces Object Storage | Bucket `hermescrm` |

Backend und Frontend sind **zwei Komponenten derselben App Platform App**
(nicht zwei getrennte Apps) – dadurch teilen sie sich eine Domain und einen
SSL-Endpunkt, unterschieden nur über den Pfad. Live-Domain:
`https://hermescrm-v9sle.ondigitalocean.app`

**SQLite ist nur noch für rein lokale Entwicklung gedacht** (`docker
compose`/lokales Entwickeln mit `CC_CRM_DATABASE_URL=sqlite:///...`) – SQLite
verträgt nur genau einen Backend-Prozess gleichzeitig. Produktiv läuft
ausschließlich Managed PostgreSQL.

## App Platform

- App-Name: `hermescrm`
- Projekt: `first-project`
- Region: Frankfurt (FRA1)
- Quelle: GitHub-Repo `gcommandeur/hermescrm`, Branch `main` (Auto-Deploy bei
  jedem Push)
- Die GitHub-App-Autorisierung für DigitalOcean ist bewusst auf genau dieses
  eine Repo beschränkt (kein kontoweiter Zugriff)

### Routing
- `/api` → Backend-Komponente `hermescrm` (Full Path Preserved, d.h.
  `/api/v1/...` kommt unverändert beim Backend an)
- `/` → Frontend-Komponente `hermescrm-frontend`

### Backend-Komponente (`hermescrm`)
- Quellverzeichnis: `/` (Root-`Dockerfile`)
- Container-Port: 8000
- Größe: 1 GB RAM / 1 shared vCPU, 1 Container (~$12/Monat) - am 2026-07-20 von
  2 auf 1 Container reduziert (CPU-Auslastung lag bei 2-4%, 2 Instanzen waren
  reine Redundanz ohne echten Bedarf bei diesem internen Nutzerkreis). Nachteil:
  kein nahtloses Rolling-Update mehr bei Deploys (kurzer Sekundenbruchteil-
  Unterbruch statt Zero-Downtime) - bei fehlendem gleichzeitigem Live-Traffic
  vernachlässigbar. Bei Bedarf jederzeit im Dashboard unter Settings →
  Resource Size wieder auf 2 Container hochsetzen.
- Health-Check: `/api/v1/health`
- Migrationen (`alembic upgrade head`) laufen automatisch als Teil des
  Start-Kommandos beim Deploy

### Frontend-Komponente (`hermescrm-frontend`)
- Quellverzeichnis: `/frontend` (eigenes `Dockerfile` dort)
- Container-Port: 3000
- Größe: 1 GB RAM / 1 shared vCPU, 1 Container (~$12/Monat) - ebenfalls am
  2026-07-20 von 2 auf 1 Container reduziert, siehe Begründung beim Backend
  oben.
- Wichtig: der `dockerfile_path` in der App Spec muss explizit auf
  `/frontend/Dockerfile` gesetzt sein – der App-Platform-Standard hätte sonst
  fälschlich das Root-Dockerfile des Backends verwendet
- `frontend/Dockerfile` kopiert `pnpm-workspace.yaml` in die deps-Stage,
  damit pnpm die dort erlaubten Build-Skripte (`sharp`, `unrs-resolver`)
  ausführt (sonst schlägt `pnpm install` mit `ERR_PNPM_IGNORED_BUILDS` fehl)

### Wo man die Einstellungen findet
DigitalOcean-Dashboard → App Platform → `hermescrm` → Tab **Settings** →
Komponente links auswählen (`hermescrm` oder `hermescrm-frontend`) → dort
Environment Variables, Routing, Ports etc.

## Datenbank (Managed PostgreSQL)

- Cluster-Name: `db-pgsql-fra1-22616`
- Region: Frankfurt (FRA1)
- Version: PostgreSQL 18
- Tier: Basic (Shared CPU), 1 vCPU / 1 GB RAM, 10 GB Storage, Autoscaling an
- Kosten: ca. $15.15/Monat
- Automatische tägliche Backups sind bei Managed PostgreSQL standardmäßig
  aktiv (kein eigenes Backup-Skript nötig)
- Netzwerkzugriff läuft über **Trusted Sources**: standardmäßig ist nur die
  App selbst eingetragen (nicht öffentlich erreichbar). Für einmalige
  Wartungsaufgaben (z.B. einen Datenumzug von einer lokalen Maschine) muss
  die eigene IPv4-Adresse temporär als Trusted Source hinzugefügt und danach
  wieder entfernt werden (Dashboard → Datenbank-Cluster → Tab **Network
  Access**→ Add Trusted Sources). Dabei zwei bekannte Stolpersteine:
  - Nur IPv4-`/32`-Einträge funktionieren zuverlässig – eine automatisch
    erkannte IPv6-Adresse oder `0.0.0.0/0` werden von DigitalOcean
    zurückgewiesen (teils nur als leicht zu übersehener Toast-Fehler). Die
    eigene IPv4 z.B. über `https://api.ipify.org?format=json` ermitteln.
  - Beim Ablesen des Passworts aus den Connection-Details: die angezeigte
    Schriftart macht Großbuchstabe `O` und Ziffer `0` optisch fast
    ununterscheidbar – im Zweifel den Text exakt kopieren statt abzutippen.
- Verbindung in der App läuft über App-Platform-interne Variablen-Referenzen
  (`${db-pgsql-fra1-22616.USERNAME}` etc.), nicht über einen fest
  eingetragenen Connection-String – Zugangsdaten liegen daher nirgends im
  Klartext in den App-Settings

### Einmaliger Datenumzug (lokale SQLite → Postgres)

Bereits erledigt für den initialen Go-Live (2026-07-20, 7.096 Zeilen über 22
Tabellen migriert), hier dokumentiert für einen eventuellen künftigen Umzug
auf einen neuen Datenbank-Cluster:

1. Ziel-Postgres-URL besorgen (Connection-Details im DO-Dashboard, siehe
   oben), Format: `postgresql+psycopg://doadmin:<passwort>@<host>:25060/defaultdb?sslmode=require`
2. Einmalig `alembic upgrade head` gegen diese URL laufen lassen (legt alle
   Tabellen an)
3. `backend/scripts/migrate_sqlite_to_postgres.py --target-url <obige URL>`
   ausführen (aus dem `backend`-Verzeichnis, mit `.venv\Scripts\python.exe`
   unter Windows – PowerShells Execution Policy blockiert oft
   `Activate.ps1`, daher die venv-`python.exe` direkt aufrufen statt zu
   aktivieren)
4. Das Skript ist idempotent (`ON CONFLICT DO NOTHING`) und unterstützt
   `--force` (falls Zieltabellen schon Zeilen enthalten, z.B. ein manuell
   angelegter Admin-User) sowie `--skip-tables <namen>` (z.B. für
   `auth_sessions` – reine Login-Token-Historie ohne Produktionswert). Bei
   verwaisten Fremdschlüsseln in nullable Spalten (z.B. eine gelöschte
   `candidate_submission`, auf die eine `activity` noch verweist) werden nur
   die einzelnen ungültigen Werte auf NULL gesetzt, nicht die ganze Zeile
   verworfen – Details siehe Skript-Docstring.
5. Nach erfolgreichem Umzug: temporäre Trusted-Source-IP wieder aus dem
   Datenbank-Cluster entfernen.

## Spaces Object Storage (Dokumente: CVs, Verträge etc.)

- Bucket-Name: `hermescrm`
- Region: Frankfurt (fra1)
- Endpoint: `https://hermescrm.fra1.digitaloceanspaces.com`
- CDN: **bewusst deaktiviert** (Kandidaten-/Kundendokumente sind vertraulich,
  sollen nicht über ein öffentliches CDN cachebar sein)
- Zugriffsschlüssel-Name: `hermes-crm-backend` (Scope: Limited Access, nur
  dieser Bucket, Read/Write/Delete)
- Wo einsehbar: DigitalOcean-Dashboard → Spaces Object Storage → Tab "Access
  Keys"
- Der Secret Access Key wird von DigitalOcean nur einmalig beim
  Erstellen/Regenerieren angezeigt und ist danach nicht mehr abrufbar. Er ist
  nur verschlüsselt als Umgebungsvariable `CC_CRM_S3_SECRET_ACCESS_KEY` in
  der Backend-Komponente hinterlegt. Falls er verloren geht: Access Key auf
  der Spaces-Seite "regenerieren" und den neuen Wert in der
  Backend-Komponente unter Environment Variables aktualisieren.

## Umgebungsvariablen (Backend-Komponente `hermescrm`)

Alle Werte außer `CC_CRM_ENVIRONMENT`, `CC_CRM_S3_BUCKET`,
`CC_CRM_S3_ENDPOINT_URL`, `CC_CRM_S3_REGION`, `CC_CRM_ANTHROPIC_MODEL` und
`CC_CRM_CORS_ORIGINS` sind als "Encrypt" markiert (im Dashboard nur maskiert
sichtbar):

- `CC_CRM_DATABASE_URL` – über Variablen-Referenzen auf den DB-Cluster
  zusammengesetzt
- `CC_CRM_ENVIRONMENT=production`
- `CC_CRM_S3_BUCKET=hermescrm`
- `CC_CRM_S3_ENDPOINT_URL=https://hermescrm.fra1.digitaloceanspaces.com`
- `CC_CRM_S3_REGION=fra1`
- `CC_CRM_S3_ACCESS_KEY_ID` (verschlüsselt)
- `CC_CRM_S3_SECRET_ACCESS_KEY` (verschlüsselt)
- `CC_CRM_ANTHROPIC_API_KEY` (verschlüsselt)
- `CC_CRM_ANTHROPIC_MODEL=claude-sonnet-5`
- `CC_CRM_CORS_ORIGINS=["https://hermescrm-v9sle.ondigitalocean.app"]`

### Transaktionale E-Mails: 2FA-Login-Codes + Sicherheitswarnungen (Resend)

Seit 2026-09-24 laufen zwei Dinge über denselben Versandweg
(`integrations/email/resend_client.py`, HTTP-API von
[Resend](https://resend.com), KEIN SMTP): der 2FA-Code bei jedem Login
(`services/auth.py`) und die Brute-Force-Sicherheitswarnung
(`services/security_alerts.py`, seit 2026-08-08 - verschickt seither pro
Brute-Force-Ausbruch genau einmal, nicht pro weiterem 429). Bewusst kein
SMTP über das verbundene M365-Postfach: M365-SMTP-Auth ist bei modernen
Tenants oft gesperrt, und nach dem Graph-Sync-Vorfall (siehe Abschnitt
unten) keine weitere M365-Abhängigkeit an dieser Stelle.

**Pflicht für den Login** (ohne diese beiden Variablen kann sich NIEMAND
mehr anmelden - der 2FA-Code kann dann nicht verschickt werden):

- `CC_CRM_RESEND_API_KEY` (verschlüsselt) – API-Key aus dem
  [Resend-Dashboard](https://resend.com/api-keys)
- `CC_CRM_RESEND_FROM_EMAIL` – Absenderadresse, z.B.
  `Hermes CRM <login@notifications.commandeur-consulting.de>` - die
  Domain muss in Resend verifiziert sein (SPF/DKIM-DNS-Einträge), sonst
  lehnt Resend den Versand ab

**Optional** (ohne gesetzte Adresse bleibt nur die Sicherheitswarnung
inaktiv - nur ein Log-Eintrag, kein Mail-Versand, bricht den Login-Flow
nie):

- `CC_CRM_SECURITY_ALERT_EMAIL` – Ziel-Adresse für Brute-Force-Warnungen
  (z.B. `gege.commandeur@gmail.com`)

### Temporäre Variable für einmalige Skript-Läufe: `CC_ARCHIV_REVIEW_CSV_B64`

`backend/scripts/delete_cc_archiv_altbestand.py` braucht die Review-CSV
(`cc_archiv_deletion_review.csv`), die per `.gitignore` bewusst NICHT im
Deploy-Image liegt (personenbezogene Daten). Fehlt die Datei lokal im
Container, rekonstruiert das Skript sie beim Start aus dieser Variable
(gzip+base64-codierte, auf die `wuerde_geloescht=ja`-Zeilen reduzierte
CSV) – Erzeugung lokal via
`python scripts/delete_cc_archiv_altbestand.py --emit-env-payload`.

- Als **Encrypt** markieren (enthält Namen echter Kandidaten)
- Nur so lange gesetzt lassen, wie der Löschlauf tatsächlich ansteht –
  danach aus den Environment Variables wieder entfernen, da sie sonst
  dauerhaft eine Kopie personenbezogener Daten außerhalb der DB in den
  App-Platform-Settings hinterlässt

### Microsoft-365-Postfach-Integration (`info@commandeurconsulting.de`)

Delegated-OAuth gegen eine Entra-ID-App-Registrierung ("HermesCRM
Postfach-Integration") - ermöglicht "Mit Microsoft anmelden" in
Einstellungen → Postfächer (Login, Senden, bidirektionaler Mail-/Kalender-
Sync für M365-Postfächer, siehe `integrations/microsoft_graph/`). Ohne diese
drei Variablen bleibt der Button funktionslos (klarer 422-Fehler statt
Absturz) - IMAP/SMTP-Postfächer sind davon nicht betroffen.

- `CC_CRM_MS_GRAPH_CLIENT_ID` – Application (client) ID der Entra-ID-App
- `CC_CRM_MS_GRAPH_TENANT_ID` – Directory (tenant) ID
- `CC_CRM_MS_GRAPH_CLIENT_SECRET` (verschlüsselt) – Client Secret aus
  "Zertifikate & Geheimnisse", läuft laut aktueller Registrierung bis
  14.09.2028 ab

Redirect-URI in Entra ID: `https://hermescrm-v9sle.ondigitalocean.app/api/v1/mail-accounts/oauth/callback`
(dieselbe Domain wie das Frontend - `/api/v1` wird per App-Platform-Routing
direkt an die Backend-Komponente weitergereicht).

**Zeitgesteuerter Sync**: `backend/scripts/run_graph_sync.py` synchronisiert
Mail + Kalender für alle `microsoft_graph`-Postfächer (Delta-Query, kein
Neuabgleich). IMAP/SMTP-Postfächer bleiben unverändert manuell über "Jetzt
abrufen" synchronisiert. Empfehlung: als App-Platform-Komponente vom Typ
**Scheduled Job**, alle 5 Minuten, Kommando `python scripts/run_graph_sync.py`
(Kosten dafür marginal, siehe M365-Integrationsplan - deutlich unter 1
$/Monat bei dieser Taktung). Diese Job-Komponente braucht dieselben
`CC_CRM_DATABASE_URL`/`CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY`/
`CC_CRM_MS_GRAPH_*`-Variablen wie die Backend-Web-Service-Komponente.

## Umgebungsvariablen (Frontend-Komponente `hermescrm-frontend`)

- `NEXT_PUBLIC_CC_CRM_API_URL=https://hermescrm-v9sle.ondigitalocean.app/api/v1`
  (Build- und Run-Time, da Next.js diesen Wert zur Build-Zeit ins
  Client-Bundle einbackt)

## Erste Anmeldung / weitere Nutzer anlegen

Es gibt keinen öffentlichen Registrierungs-Endpunkt (bewusst – das CRM ist
nicht für Selbstregistrierung gedacht). Logins werden über
`backend/scripts/create_test_user.py` angelegt (Name ist historisch – das
Skript legt jeden Login mit E-Mail + Passwort an oder aktualisiert dessen
Passwort):

```
python scripts/create_test_user.py deine-email@commandeurconsulting.de <dein-passwort>
```

Optional als dritter Parameter ein Anzeigename (ohne Angabe bleibt es beim
Default "Test User") – so lässt sich derselbe Befehl für jeden weiteren
Kollegen wiederholen:

```
python scripts/create_test_user.py kollege@commandeurconsulting.de <passwort> "Anzeigename"
```

Admin-Rechte und Aktiv-Status lassen sich danach im laufenden Betrieb unter
**Einstellungen → Nutzerverwaltung** in der CRM-Oberfläche selbst verwalten
(kein erneuter Skript-Aufruf nötig).

## Kalender-Sync (Outlook)

Jeder Nutzer findet unter **Einstellungen** eine persönliche,
schreibgeschützte ICS-Feed-URL (`/api/v1/calendar/feed/<token>.ics`), die nur
die eigenen Termine enthält (Interviews, Quali-Calls, sonstige Termine).
Diese URL ist geheim wie ein Passwort und lässt sich bei Bedarf über "Feed-URL
neu generieren" invalidieren. Einbindung in Outlook (Desktop oder Web) über
"Kalender hinzufügen → Aus dem Internet/Web abonnieren".

## Was NICHT automatisch passiert

- **Monitoring/Alerting**: Für den Anfang reicht der eingebaute Healthcheck
  (`/api/v1/health`); für echten Betrieb später ggf. Uptime-Monitoring (z.B.
  UptimeRobot, kostenlos) ergänzen.
- **E-Mail-Versand** (Outlook-Integration über den Kalender-Sync hinaus):
  laut Projektstand für eine spätere Phase vorgesehen, nicht Teil dieses
  Deployments.
- **Datenbereinigung**: Die lokale Entwicklungs-Historie enthielt einzelne
  Dateninkonsistenzen (z.B. verwaiste Fremdschlüssel-Verweise), die beim
  Produktiv-Umzug sanitisiert statt blockierend behandelt wurden – siehe
  offene Aufgabe "Daten-Hygiene" im Projekt-Cockpit für eine systematische
  Bereinigung.

## Sicherheits-Check

- Alle Kandidaten-/Kanzlei-/Dokument-Endpunkte verlangen einen gültigen Login
  (Bearer-Token) oder API-Key – global über `protected_router` in
  `api/v1/router.py` erzwungen, nicht pro Endpunkt einzeln.
- Passwörter werden mit PBKDF2-SHA256 (260.000 Iterationen, zufälliges Salt
  pro Passwort) gehasht, nie im Klartext gespeichert.
- Login-Sessions: der Token wird nur als SHA-256-Hash in der Datenbank
  gespeichert, nicht im Klartext – ein Datenbank-Leak allein würde keine
  aktiven Sessions kompromittieren.
- Fehlermeldungen an die Öffentlichkeit sind auf definierte, harmlose
  Meldungen begrenzt (kein Roh-Traceback, keine internen Pfade/Variablen).
- `.env`-Dateien sowie `backend/data/documents/` und `backend/data/imports/`
  (echte Kandidaten-/Kanzleidaten) sind in `.gitignore` – werden nicht ins
  Repo committet.
- API-Dokumentation nur außerhalb Produktion: `/docs`, `/redoc` und
  `/openapi.json` liefern bei `CC_CRM_ENVIRONMENT=production` 404
  (`main.py::create_app`).
- Rate-Limiting auf dem Login-Endpunkt: nach 3 fehlgeschlagenen
  Login-Versuchen derselben Client-IP innerhalb von 5 Minuten liefert
  `/api/v1/auth/login` 429 (`core/rate_limit.py`, `MAX_ATTEMPTS`/`WINDOW`).
  Die Client-IP wird primär aus `CF-Connecting-IP` gelesen (von Cloudflare
  selbst am Edge gesetzt, vom Client nicht fälschbar) - **nicht** mehr aus
  dem ersten `X-Forwarded-For`-Eintrag: der ist vom Client frei wählbar und
  erlaubte bis 2026-08-08 eine vollständige Umgehung des Rate-Limits durch
  einen bei jedem Request neu erfundenen Header-Wert (live auf Produktion
  bestätigt und seitdem behoben, siehe Git-History `core/rate_limit.py`).
  Löst das Limit für eine IP aus, geht zusätzlich einmalig eine
  Sicherheitswarnung per E-Mail raus (siehe
  "Sicherheitswarnungen per E-Mail" oben) - vorausgesetzt, die SMTP-Variablen
  sind gesetzt.
- Datenbank nicht öffentlich erreichbar, nur über Trusted-Source-Bindung zur
  App selbst.
- GitHub-Zugriff für DigitalOcean auf genau ein Repo beschränkt statt
  kontoweitem Zugriff.
- Kein CDN vor dem Dokumentenspeicher (Vertraulichkeit vor Ladegeschwindigkeit
  für CV-/Vertragsdaten).
- Secrets (API-Keys, DB-Zugangsdaten, Access Keys) ausschließlich als
  verschlüsselte App-Platform-Umgebungsvariablen, nirgends im Klartext in
  Doku oder Repo.

## Kosten (Stand 2026-07-20, nach Reduzierung auf je 1 Container)

- App Platform Backend: ~$12/Monat (1 Container)
- App Platform Frontend: ~$12/Monat (1 Container)
- Managed PostgreSQL: ~$15.15/Monat
- Spaces Object Storage: nach Verbrauch (Basistarif meist wenige Dollar/Monat
  bei diesem Datenvolumen)

Gesamt: ca. $39-40/Monat laufend. Ursprünglich liefen beide App-Platform-
Komponenten mit je 2 Containern (~$63-65/Monat gesamt) für Redundanz bei
Deployments - bei der tatsächlichen Auslastung (2-4% CPU) unnötig, siehe
Begründung bei den jeweiligen Komponenten oben.

Bitte aktuelle Preise im DigitalOcean-Dashboard prüfen, da sich Tarife ändern
können.
