# Hermes CRM – Deployment-Anleitung

Diese Anleitung beschreibt den empfohlenen, einfachen Weg, Hermes CRM produktiv
zu hosten. Alle Schritte, die ein Konto, eine Zahlung oder Zugangsdaten
betreffen, musst du selbst ausführen (Claude/Cowork legt aus Sicherheitsgründen
keine Accounts an und gibt keine Zahlungsdaten ein).

## Empfohlener Stack (einfach, günstig, passend zur aktuellen Größe)

| Komponente | Empfehlung | Warum |
|---|---|---|
| Backend (FastAPI) | [Railway](https://railway.app) oder [Render](https://render.com) | Docker-Image direkt deploybar, einfaches Setup |
| Frontend (Next.js) | [Vercel](https://vercel.com) | Von den Next.js-Machern, null Konfiguration, automatisches HTTPS/CDN |
| Dokumente (CVs, Verträge) | [Cloudflare R2](https://developers.cloudflare.com/r2/) | S3-kompatibel, kein Ausgangsdatenverkehr-Aufpreis (egress-frei), günstig |
| Datenbank | **Managed PostgreSQL** (Railway-Addon oder Supabase) | Produktionsempfehlung - echte Nebenläufigkeit (mehrere Backend-Instanzen, spätere Mobile-App mit gleichzeitigen Verbindungen), kein Volume-Management nötig, automatische Backups beim Anbieter. Siehe Schritt 1a unten für die Einrichtung. |

**SQLite ist nur noch für rein lokale Entwicklung gedacht**, nicht mehr als
Produktionsempfehlung: SQLite verträgt sich nur mit GENAU EINEM
Backend-Prozess gleichzeitig (kein horizontales Skalieren, kein Zugriff durch
mehrere Instanzen). Der Code unterstützt SQLite weiterhin unverändert für
`docker compose`/lokales Entwickeln (`CC_CRM_DATABASE_URL=sqlite:///...`),
für den produktiven Cloud-Betrieb aber bitte Postgres verwenden (Schritt 1a).
Das Projekt ist bereits vollständig auf Postgres vorbereitet (Treiber,
Alembic-Migrationen, Umzugsskript) - Details siehe unten.

## Schritt 1 – Cloudflare R2 einrichten (Dokumentenspeicher)

1. Cloudflare-Account erstellen/einloggen: https://dash.cloudflare.com
2. R2 aktivieren, einen Bucket anlegen (z.B. `hermes-crm-documents`)
3. Unter "Manage R2 API Tokens" einen API-Token mit Schreibrechten für diesen
   Bucket erstellen
4. Diese Werte notieren (werden in Schritt 3 als Umgebungsvariablen gebraucht):
   - Account-ID
   - Access Key ID
   - Secret Access Key
   - Endpoint-URL (Format: `https://<account-id>.r2.cloudflarestorage.com`)

## Schritt 1a – PostgreSQL-Instanz anlegen (Datenbank)

Zwei gängige, einfache Optionen - beide reichen für den Start:

**Option A: Railway-Postgres-Addon** (praktisch, wenn das Backend ohnehin auf
Railway läuft - eine Rechnung, ein Dashboard):
1. Im Railway-Projekt "New" → "Database" → "Add PostgreSQL" wählen
2. Railway legt automatisch eine `DATABASE_URL`-Variable im Projekt an
   (Format `postgresql://user:pass@host:port/railway`) - für
   `CC_CRM_DATABASE_URL` das Präfix auf `postgresql+psycopg://` ändern
   (SQLAlchemy braucht den Treiber-Namen im Schema), Rest unverändert
   übernehmen.

**Option B: Supabase** (kostenloser Tier reicht für den Start, praktisch bei
Bedarf für spätere Zusatzfeatures wie Auth/Storage):
1. Auf https://supabase.com Projekt anlegen
2. Unter Project Settings → Database → Connection string den "URI"-String
   kopieren (Format `postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres`)
3. Für `CC_CRM_DATABASE_URL` ebenfalls das Präfix auf
   `postgresql+psycopg://` ändern.

In beiden Fällen: die fertige URL wird in Schritt 2 als
`CC_CRM_DATABASE_URL` gesetzt. Danach einmalig `alembic upgrade head` gegen
diese URL laufen lassen (legt alle Tabellen an), und falls bereits lokale
SQLite-Daten existieren, `backend/scripts/migrate_sqlite_to_postgres.py`
(siehe Skript-Docstring) für den einmaligen Datenumzug verwenden.

## Schritt 2 – Backend hosten (Railway, Beispiel)

1. Auf https://railway.app einloggen, neues Projekt erstellen
2. "Deploy from GitHub repo" wählen und das Hermes-CRM-Repo verbinden
   (Railway erkennt automatisch das `Dockerfile` im Repo-Root)
3. **Kein Volume nötig** für die Datenbank selbst (Postgres läuft managed,
   siehe Schritt 1a) - nur falls weiterhin lokale Dokumente statt R2
   verwendet würden, wäre ein Volume relevant (bei R2-Konfiguration wie
   unten nicht der Fall).
4. Umgebungsvariablen setzen (Railway-Projekt -> Variables):
   ```
   CC_CRM_ENVIRONMENT=production
   CC_CRM_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname
   CC_CRM_CORS_ORIGINS=["https://DEINE-FRONTEND-DOMAIN.vercel.app"]
   CC_CRM_ANTHROPIC_API_KEY=<dein Anthropic API Key>
   CC_CRM_ANTHROPIC_MODEL=claude-sonnet-5
   CC_CRM_S3_BUCKET=hermes-crm-documents
   CC_CRM_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
   CC_CRM_S3_REGION=auto
   CC_CRM_S3_ACCESS_KEY_ID=<aus Schritt 1>
   CC_CRM_S3_SECRET_ACCESS_KEY=<aus Schritt 1>
   ```
5. Deployen. Railway baut das Dockerfile, startet den Container; Migrationen
   laufen automatisch beim Start (`alembic upgrade head` ist Teil des
   Start-Kommandos).
6. Die vergebene Railway-Domain (oder eine eigene Domain) notieren - das ist
   die Backend-URL, die das Frontend braucht.

*Falls du lieber Render nutzt: gleiches Prinzip (Dockerfile erkennen lassen,
dieselben Umgebungsvariablen setzen - kein Persistent Disk nötig, da weder
Datenbank noch Dokumente lokal gespeichert werden).*

## Schritt 3 – Frontend hosten (Vercel)

1. Auf https://vercel.com einloggen, "Add New Project", das Repo verbinden
2. Root Directory auf `frontend/` setzen
3. Vercel erkennt Next.js automatisch (kein Dockerfile nötig - Vercel baut
   nativ). Das `frontend/Dockerfile` ist als Alternative vorhanden, falls du
   stattdessen auf einer Docker-basierten Plattform hosten willst.
4. Umgebungsvariable setzen:
   ```
   NEXT_PUBLIC_CC_CRM_API_URL=https://DEINE-BACKEND-DOMAIN.up.railway.app/api/v1
   ```
5. Deployen. Vercel vergibt automatisch eine `*.vercel.app`-Domain (eigene
   Domain später unter Projekteinstellungen -> Domains ergänzbar).
6. Zurück zu Railway/Render: `CC_CRM_CORS_ORIGINS` mit der finalen
   Vercel-Domain aktualisieren (Schritt 2.4), damit das Backend Anfragen vom
   Frontend akzeptiert.

## Schritt 4 – Erste Anmeldung / Nutzer anlegen

Es gibt keinen öffentlichen Registrierungs-Endpunkt (bewusst - das CRM ist
nicht für Selbstregistrierung gedacht). Der erste Login wird über
`backend/scripts/create_test_user.py` angelegt (Name ist historisch - das
Skript legt jeden Login mit E-Mail + Passwort an oder aktualisiert dessen
Passwort, nicht nur "Testnutzer"):

```
python scripts/create_test_user.py deine-email@commandeurconsulting.de <dein-passwort>
```

Optional kann als dritter Parameter ein Anzeigename mitgegeben werden (ohne
Angabe bleibt es beim Default "Test User") - so lässt sich derselbe Befehl
für jeden weiteren Kollegen mit eigenem Namen wiederholen:

```
python scripts/create_test_user.py kollege@commandeurconsulting.de <passwort> "Anzeigename"
```

Auf einer gehosteten Plattform wie Railway kannst du diesen Befehl einmalig
über die dortige Shell/Console des Deployments ausführen (z.B. Railway's
"Run a command" in der Service-Ansicht), da das Skript direkt gegen die
laufende Datenbank arbeitet.

## Was NICHT automatisch passiert

- **Backups**: `scripts/backup_to_s3.py` sichert nur eine lokale SQLite-Datei
  (Pfad aus `CC_CRM_DATABASE_URL`) - das ist also nur für rein lokale
  Entwicklung relevant, **nicht** für den produktiven Postgres-Betrieb (das
  Skript lehnt eine Postgres-URL bewusst ab, siehe Skript-Docstring: für eine
  laufende Server-Datenbank ist `pg_dump`/der Backup-Mechanismus des
  Postgres-Anbieters der richtige Weg, kein Datei-Upload). Railway- und
  Supabase-Postgres bringen beide automatische, tägliche Backups bereits im
  Dashboard mit - dort aktivieren/prüfen statt eines eigenen Skripts.
- **Monitoring/Alerting**: Für den Anfang reicht der eingebaute Healthcheck
  (`/api/v1/health`); für echten Betrieb später ggf. Uptime-Monitoring (z.B.
  UptimeRobot, kostenlos) ergänzen.
- **E-Mail-Versand** (Outlook-Integration): laut Projektstand für eine
  spätere Phase vorgesehen, nicht Teil dieses Deployments.

## Sicherheits-Check (bereits geprüft)

- Alle Kandidaten-/Kanzlei-/Dokument-Endpunkte verlangen einen gültigen Login
  (Bearer-Token) oder API-Key - global über `protected_router` in
  `api/v1/router.py` erzwungen, nicht pro Endpunkt einzeln (also auch für die
  neuen Dokument-Upload/Download-Endpunkte automatisch mit abgesichert).
- Passwörter werden mit PBKDF2-SHA256 (260.000 Iterationen, zufälliges Salt
  pro Passwort) gehasht, nie im Klartext gespeichert.
- Login-Sessions: der Token wird nur als SHA-256-Hash in der Datenbank
  gespeichert, nicht im Klartext - ein Datenbank-Leak allein würde keine
  aktiven Sessions kompromittieren.
- Fehlermeldungen an die Öffentlichkeit sind auf definierte, harmlose
  Meldungen begrenzt (kein Roh-Traceback, keine internen Pfade/Variablen).
- `.env`-Dateien sowie `backend/data/documents/` und `backend/data/imports/`
  (echte Kandidaten-/Kanzleidaten) sind in `.gitignore` - werden nicht ins
  Repo committet.

## Vor Go-Live umgesetzt (Stand 2026-07-16)

- **API-Dokumentation nur außerhalb Produktion**: `/docs`, `/redoc` und
  `/openapi.json` sind nur erreichbar, wenn `CC_CRM_ENVIRONMENT` `local`
  oder `development` ist - bei `production` liefern alle drei 404
  (`main.py::create_app`).
- **Rate-Limiting auf dem Login-Endpunkt**: einfacher, prozessinterner
  In-Memory-Zähler (`core/rate_limit.py`) - nach 5 fehlgeschlagenen
  Login-Versuchen derselben Client-IP innerhalb von 5 Minuten liefert
  `/api/v1/auth/login` 429, bevor überhaupt ein Passwort-Vergleich
  stattfindet. Ein erfolgreicher Login setzt den Zähler für diese IP sofort
  zurück. Kein Redis nötig - reicht für einen einzelnen uvicorn-Prozess und
  einen kleinen internen Nutzerkreis.
- **Automatisiertes Datenbank-Backup**: siehe `scripts/backup_to_s3.py`
  oben - das Skript selbst ist fertig, nur der Zeitplan (Cron) muss beim
  gewählten Hosting-Anbieter eingerichtet werden.
- **PostgreSQL-Vorbereitung**: Treiber (`psycopg[binary]`), Alembic-Migrationen
  und Session-Setup sind bereits dialektübergreifend (SQLite lokal, Postgres
  produktiv) getestet; `backend/scripts/migrate_sqlite_to_postgres.py` kopiert
  den bestehenden lokalen Datenbestand einmalig in eine neue Postgres-Instanz,
  sobald diese angelegt ist (Schritt 1a).

## Kosten-Richtwert (Stand heute, kann sich ändern)

- Railway: kleine Backend-Instanz + Postgres-Addon, ca. 5-20 $/Monat je nach
  Nutzung (Postgres-Addon selbst hat einen kleinen kostenlosen Anteil)
- Supabase: kostenloser Tier reicht für den Start (Postgres-Datenbank
  inklusive), danach nutzungsabhängig
- Vercel: kostenloser "Hobby"-Plan reicht für den Anfang
- Cloudflare R2: erste 10 GB Speicher kostenlos, danach sehr günstig (kein
  Ausgangsdatenverkehr-Aufpreis)

Bitte aktuelle Preise auf den jeweiligen Anbieter-Websites prüfen, bevor du
dich endgültig entscheidest.
