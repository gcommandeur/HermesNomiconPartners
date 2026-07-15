# CC CRM: Ist-Analyse und Zielarchitektur

Stand: 28.06.2026

## 1. Analysierter Ausgangsstand

Das aktuelle Ist-System ist die separat abgelegte Streamlit-/SQLite-
Legacy-Anwendung. Daneben existieren ein unveränderlicher Stable-Snapshot und
eine Arbeitskopie für frühere Prototypänderungen.

Diese Mehrfachablage macht die Quelle der Wahrheit unklar. Vor einer Migration
muss ein kanonisches Repository festgelegt werden. Der Stable-Snapshot bleibt
nur als unveränderliches Archiv erhalten.

### Technischer Bestand

- Streamlit-Monolith mit rund 2.300 Zeilen in `app.py`
- SQLite-Zugriff und Schemaerzeugung in `crm_database.py`
- Dokumente, Volltextsuche, CV-Parsing, Mailings und Microsoft Graph in
  `enterprise_features.py`
- SQL wird unmittelbar aus UI-nahen Funktionen aufgerufen.
- Tabellen werden beim Start erzeugt und teilweise verändert.
- Demo-Daten werden beim Start automatisch angelegt.
- Keine automatisierten Unit-, Integrations- oder API-Tests
- Keine versionierten Datenbankmigrationen
- Keine interne Benutzer-, Rollen- oder Mandantenlogik
- Deployment ist auf eine einzelne Streamlit-/SQLite-Instanz begrenzt.

## 2. Was aktuell gut ist

- Recruiting-spezifische Begriffe und Abläufe sind bereits sichtbar.
- Kandidaten, Kanzleien, Prozesse, Statushistorie und Follow-ups existieren.
- Jede Statusänderung erzeugt grundsätzlich einen Historieneintrag.
- Follow-up-Fristen sind konfigurierbar.
- Dokumente werden Kandidaten und Kanzleien zugeordnet.
- PDF-, DOCX- und TXT-Inhalte können ausgelesen und durchsucht werden.
- Microsoft Graph erstellt nur Outlook-Entwürfe und versendet nicht automatisch.
- Zugangstoken stehen nicht hardcoded im Quelltext.
- Parameterisierte SQL-Abfragen werden überwiegend korrekt verwendet.
- Die bestehende Anwendung ist als Referenz für Verhalten und Fachsprache
  wertvoll.

## 3. Was problematisch ist

### Architektur

- UI, Validierung, Business-Logik, Datenzugriff und Integrationen sind eng
  gekoppelt.
- Große Module besitzen zu viele Verantwortlichkeiten.
- Pandas-DataFrames dienen als implizite Verträge zwischen Datenbank und UI.
- Es gibt keine stabile REST-API und keine versionierten Schemas.
- Änderungen an importierten Python-Modulen erfordern teilweise einen
  Prozessneustart.

### Datenmodell

- `processes` vermischt interne Kandidaten-Pipeline und Kundenvorstellung.
- CV-Out/CandidateSubmission ist kein eigenes Kernobjekt.
- `create_cv_out_process()` speichert die Kanzlei nicht zuverlässig als
  relationale Submission-Zuordnung.
- Ansprechpartner sind Felder an der Kanzlei statt eigener Datensätze.
- Standorte sind kommaseparierte Texte statt normalisierter Kanzleistandorte.
- Statuswerte und IDs sind frei formatierte Texte.
- Historien speichern Kandidaten- und Kanzleinamen redundant als Snapshots.
- Dokumentbeziehungen verwenden `entity_type` und `entity_key` ohne Foreign Key.
- Jobs/Mandate, Interviews, Offers, Placements, Fees und Rechnungen fehlen als
  eigenständige relationale Objekte.
- BLOBs in SQLite sind für die geplante Dokumentmenge nicht geeignet.

### Betrieb und Sicherheit

- SQLite begrenzt Parallelität, Skalierung und mehrere App-Instanzen.
- Schemaänderungen werden zur Laufzeit statt über Migrationen ausgeführt.
- `initialize_database()` verändert beim Start aktive Prozessdaten.
- Demo-Seeding läuft im Anwendungsstart und gehört nicht in Produktion.
- Anwendungsschutz wird aktuell an die Azure-Plattform delegiert; API-seitige
  Rollenprüfung und Audit fehlen.
- Statische Graph-Token sind nur als Testweg vorgesehen, aber der produktive
  OAuth-Lebenszyklus ist noch nicht implementiert.
- Keine Background Jobs für Parsing, Mail-Synchronisierung oder Webhooks.
- Keine Observability, strukturierten Logs, Metriken oder Error-IDs.

## 4. Was refactored werden sollte

1. Fachmodell und Statusautomaten unabhängig von Streamlit formulieren.
2. CandidateSubmission als eigenes Aggregat einführen.
3. Datenbankzugriff hinter Repository-Schnittstellen kapseln.
4. Business-Regeln in Services und Use Cases verschieben.
5. FastAPI mit versionierten Pydantic-Schemas als stabile Systemgrenze
   einführen.
6. PostgreSQL und Alembic als einziges produktives Persistenzmodell verwenden.
7. Dateien in Object Storage speichern; nur Metadaten und Storage-Key gehören
   in PostgreSQL.
8. Externe Anbieter ausschließlich über Ports/Adapter anbinden.
9. Authentifizierung, Autorisierung und Audit serverseitig erzwingen.
10. Automatisierte Tests vor der Datenmigration aufbauen.

## 5. Was nicht weiter ausgebaut werden sollte

- Keine neuen produktiven Features direkt in `app.py`.
- Keine weiteren `CREATE TABLE`- oder `ALTER TABLE`-Blöcke im App-Start.
- Keine zusätzlichen BLOB-Dokumente in der produktiven SQL-Datenbank.
- Keine direkte Microsoft-, Gmail-, LinkedIn- oder Bullhorn-Logik in Routern
  oder UI-Komponenten.
- Keine neue Business-Logik in Streamlit-Callbacks.
- Keine produktive Skalierung der SQLite-Version.
- Keine echte personenbezogene Information in Seeds, Fixtures oder Screenshots.

## 6. Professionelle Zielarchitektur

```text
Browser
  |
  v
Next.js Web App
  |
  | HTTPS / REST / OpenAPI client
  v
FastAPI Application
  |-- Routers: HTTP, Auth, Pagination, Error Mapping
  |-- Application Services: Use Cases und Transaktionen
  |-- Domain: Entities, Value Objects, Policies, Events
  |-- Repositories: Persistenz-Ports
  |-- Integrations: Anbieter-Adapter
  |
  +--> PostgreSQL
  +--> Object Storage
  +--> Queue / Worker
  +--> Microsoft Entra ID
```

### Leitlinien

- API-first und versioniert unter `/api/v1`
- OpenAPI ist der Vertrag zwischen Backend und Frontend.
- Aus OpenAPI wird ein typisierter TypeScript-Client generiert.
- Domain und Application Layer kennen weder FastAPI noch externe Anbieter.
- Transaktionen werden im Service-/Unit-of-Work-Layer gesteuert.
- Zeitangaben werden als UTC gespeichert und lokal formatiert.
- Primärschlüssel sind UUIDs; externe IDs werden separat und eindeutig geführt.
- Listen verwenden Cursor- oder Offset-Pagination, Filter und Sortierung.
- Langläufer laufen in einem Worker und liefern Job-Status zurück.
- Jeder schreibende Use Case erzeugt Audit- und relevante Activity-Einträge.

## 7. Vorgesehene Ordnerstruktur

```text
backend/
  pyproject.toml
  alembic.ini
  alembic/
    env.py
    versions/
  src/cc_crm/
    main.py
    core/
      config.py
      security.py
      errors.py
      logging.py
    api/
      dependencies.py
      error_handlers.py
      v1/
        router.py
        candidates.py
        clients.py
        contacts.py
        jobs.py
        submissions.py
        interviews.py
        offers.py
        placements.py
        tasks.py
        documents.py
        communications.py
        fees.py
    domain/
      candidates/
      clients/
      jobs/
      submissions/
      activities/
      billing/
    application/
      services/
      commands/
      queries/
      ports/
      unit_of_work.py
    infrastructure/
      database/
        models/
        repositories/
        session.py
      storage/
      queue/
    integrations/
      gmail/
      calendar/
      bullhorn/
      linkedin/
      webhooks/
      ai/
      microsoft_graph/
  tests/
    unit/
    integration/
    api/

frontend/
  package.json
  next.config.ts
  src/
    app/
      (dashboard)/
        candidates/
        clients/
        jobs/
        pipeline/
        tasks/
        mailings/
        settings/
    components/
      ui/
      layout/
      data-table/
      pipeline/
      forms/
    features/
      candidates/
      clients/
      jobs/
      submissions/
      activities/
    lib/
      api/
      auth/
      validation/
      formatting/
    hooks/
    types/
  tests/

docs/
  CC_CRM_ARCHITECTURE.md
  api/
  adr/

legacy/
  streamlit/
```

`legacy/streamlit` wird erst angelegt, wenn Importpfade, Startskripte und
Backups kontrolliert umgestellt werden. Die aktuelle Anwendung wird bis dahin
nicht verschoben.

## 8. Relationaler Datenbankentwurf

### Identität und Organisation

**users**

- `id UUID PK`
- `entra_subject`, `email`, `display_name`
- `is_active`, `created_at`, `updated_at`

**roles**, **user_roles**

- Rollen wie Admin, Recruiter, Research, Finance, ReadOnly

### Kandidaten

**candidates**

- Stammdaten, Kontaktinformationen, Ort, Gehaltsvorstellung
- Kündigungsfrist, Verfügbarkeit, Datenschutzstatus
- interner Lifecycle-Status und zuständiger Recruiter

**candidate_experiences**

- Arbeitgeber, Rolle, Fachgebiet, Beginn/Ende, Beschreibung

**candidate_skills**

- normalisierte Skills mit Erfahrungsniveau

### Kunden und Mandate

**clients**

- Kanzlei/Kunde, Status, Website, Sperrstatus und Owner

**client_locations**

- Straße, PLZ, Ort, Land, Geo-Koordinaten

**contacts**

- gehört zu einem Client, besitzt Rolle, E-Mail, Telefon und Präferenzen

**jobs**

- Mandat, Client, Standort, Titel, Fachgebiet, Seniorität
- Gehaltsband, Fee-Modell, Status, zuständiger Recruiter

### CandidateSubmission als Kernobjekt

**candidate_submissions**

- `id UUID PK`
- `candidate_id FK NOT NULL`
- `client_id FK NOT NULL`
- `job_id FK NULL` für spekulative Vorstellungen
- `primary_contact_id FK NULL`
- `status`
- `submitted_at`, `last_activity_at`, `closed_at`
- `source`, `owner_user_id`
- eindeutige fachliche Regeln gegen doppelte aktive Vorstellungen

Der implementierte Statusautomat verwendet:

`draft`, `sent`, `client_review`, `feedback_pending`, `interview_requested`,
`interview_scheduled`, `rejected`, `offer_expected`, `offer_received`,
`placed`, `withdrawn`, `cancelled`.

Statusänderungen erfolgen ausschließlich über einen Transition-Service und
erzeugen sowohl eine fachliche Activity als auch einen technischen AuditLog.

**submission_status_events**

- Submission, alter/neuer Status, Zeitpunkt, Actor, Grund, Kommentar
- append-only; bildet die fachliche Historie

**submission_feedback**

- Feedback des Kunden oder Kandidaten, Richtung, Ergebnis, Zeitpunkt

**interviews**

- Submission, Runde, Start/Ende, Ort/Meeting-Link, Status, Feedback

**offers**

- Submission, Betrag, Währung, Startdatum, Status, Bedingungen

**placements**

- Submission, Kandidat, Client, Job, Startdatum, Jahresgehalt
- Garantiezeitraum und Placement-Status

**fees**

- Placement, Fee-Typ, Prozent/Festbetrag, Nettobetrag, Währung
- Rechnungsstatus, Rechnungsnummer, Fälligkeit, Zahlungseingang

### Arbeit und Kommunikation

**tasks**

- Titel, Status, Priorität, Fälligkeit, Owner
- optionale FKs zu Candidate, Client, Job oder Submission

**follow_ups**

- Submission/Task, Regel, Fälligkeit, erledigt/verschoben

**notes**

- Inhalt, Autor, Sichtbarkeit, fachliche Zuordnung

**activities**

- append-only Timeline für Statuswechsel, Calls, Mails, Uploads und Termine

**documents**

- Dateiname, MIME-Type, Größe, Hash, Storage-Key, Klassifikation

**document_links**

- explizite Zuordnung zu Candidate, Client, Job oder Submission

**email_messages**

- Provider-ID, Thread-ID, Richtung, Absender, Empfänger, Betreff, Zeit
- Zustellstatus und Zuordnung zum CRM-Objekt

**calendar_events**

- Provider-ID, Beginn/Ende, Zeitzone, Ort/Link und CRM-Zuordnung

**audit_log**

- Actor, Aktion, Objekt, Objekt-ID, Zeit, Request-ID und Änderungen

## 9. Wichtige API-Endpunkte

### System und Auth

- `GET /health`
- `GET /api/v1/me`
- `GET /api/v1/meta/pipeline-stages`

### Kandidaten

- `GET /api/v1/candidates`
- `POST /api/v1/candidates`
- `GET /api/v1/candidates/{candidate_id}`
- `PATCH /api/v1/candidates/{candidate_id}`
- `GET /api/v1/candidates/{candidate_id}/timeline`
- `GET /api/v1/candidates/{candidate_id}/submissions`
- `POST /api/v1/candidates/imports`

### Kanzleien und Kontakte

- `GET|POST /api/v1/clients`
- `GET|PATCH /api/v1/clients/{client_id}`
- `GET|POST /api/v1/clients/{client_id}/locations`
- `GET|POST /api/v1/clients/{client_id}/contacts`
- `PATCH /api/v1/contacts/{contact_id}`

### Jobs/Mandate

- `GET|POST /api/v1/jobs`
- `GET|PATCH /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_id}/submissions`

### Candidate Submissions

- `GET|POST /api/v1/submissions`
- `GET|PATCH /api/v1/submissions/{submission_id}`
- `POST /api/v1/submissions/{submission_id}/transitions`
- `GET /api/v1/submissions/{submission_id}/timeline`
- `POST /api/v1/submissions/{submission_id}/feedback`
- `POST /api/v1/submissions/{submission_id}/interviews`
- `POST /api/v1/submissions/{submission_id}/offers`
- `POST /api/v1/submissions/{submission_id}/placements`
- `POST /api/v1/submissions/{submission_id}/close`

Statusänderungen erfolgen ausschließlich über `transitions`, nicht über ein
beliebiges Status-PATCH. Dadurch bleiben Regeln, Historie und Follow-ups
konsistent.

### Aufgaben, Dokumente und Kommunikation

- `GET|POST /api/v1/tasks`
- `PATCH /api/v1/tasks/{task_id}`
- `POST /api/v1/documents/presign`
- `POST /api/v1/documents`
- `GET /api/v1/documents/{document_id}/download`
- `GET /api/v1/activities`
- `GET /api/v1/email-messages`
- `POST /api/v1/mail-drafts`
- `GET|POST /api/v1/calendar-events`

### Fees

- `GET /api/v1/fees`
- `POST /api/v1/placements/{placement_id}/fees`
- `PATCH /api/v1/fees/{fee_id}`

### Integrationen

- `GET /api/v1/integrations`
- `POST /api/v1/integrations/{provider}/connect`
- `POST /api/v1/webhooks/{provider}`
- `POST /api/v1/search/ai`

Webhooks validieren Signaturen, speichern Provider-Events idempotent und
delegieren die Verarbeitung an Background Jobs.

## 10. Inkrementeller Refactoring-Plan

### Phase 0: Stabilisieren und vermessen

1. Kanonisches Repository und Datenverzeichnis festlegen.
2. Aktuelle SQLite-Datenbank sichern und Prüfsummen dokumentieren.
3. Bestehendes Verhalten mit Characterization Tests abdecken.
4. Keine neuen produktiven Features im Streamlit-Monolithen.

### Phase 1: Backend-Grundgerüst

1. FastAPI-Projekt mit Konfiguration, Logging und Healthcheck anlegen.
2. PostgreSQL, SQLAlchemy 2 und Alembic konfigurieren.
3. Testcontainer beziehungsweise isolierte Testdatenbank einrichten.
4. Entra-ID-Claims und Rollen als API-Abhängigkeiten vorbereiten.

### Phase 2: Read-only Strangler API

1. Kandidaten- und Client-Modelle plus Migrationen erstellen.
2. Read-only Import der SQLite-Daten in PostgreSQL entwickeln.
3. Listen- und Detail-Endpunkte implementieren.
4. Datenmengen und Abfragepläne mit synthetischen Daten testen.

### Phase 3: Recruiting-Kern

1. Jobs und CandidateSubmissions modellieren.
2. Statusautomat und Submission-Historie implementieren.
3. Interviews, Offers, Placements und Fees ergänzen.
4. Follow-up-Policy als Domain Service implementieren.

### Phase 4: Next.js-Frontend

1. App-Shell, Sidebar, Auth und Design Tokens aufbauen.
2. Kandidaten- und Kanzleilisten gegen die API erstellen.
3. Detailansichten und Timeline ergänzen.
4. Submission-Pipeline/Kanban mit serverseitigen Transitionen bauen.

### Phase 5: Dokumente und Kommunikation

1. Object Storage und asynchrones Parsing anbinden.
2. Microsoft Graph über einen Adapter mit OAuth integrieren.
3. E-Mail-Threads, Kalender und Webhooks idempotent synchronisieren.
4. Gmail-, Bullhorn-, LinkedIn- und AI-Ports zunächst als Interfaces anlegen.

### Phase 6: Umschalten

1. Vollständigen Probeimport und fachlichen Abgleich durchführen.
2. Delta-/Freeze-Migration planen.
3. Rollen, Audit, Backups, Restore und Monitoring abnehmen.
4. Next.js/FastAPI produktiv schalten.
5. Streamlit nur noch read-only als zeitlich begrenzten Fallback behalten.

## 11. Abnahmekriterien für den ersten Code-Schritt

Die Implementierung von Phase 1 beginnt erst, wenn folgende Entscheidungen
feststehen:

- kanonischer Projektpfad
- PostgreSQL-Betriebsort
- Object-Storage-Anbieter
- Entra-ID-Tenant und Rollenmodell
- Job/Submission-Statusmodell
- Aufbewahrungs- und Löschfristen für Bewerberdaten

Bis dahin bleibt die laufende Streamlit-Anwendung unverändert verfügbar.
