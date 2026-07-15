# CC CRM Audit Report

**Audit-Datum:** 28.06.2026  
**Audit-Gegenstand:** neues CC-CRM-Backend und -Frontend  
**Nicht Gegenstand:** Streamlit-/SQLite-Legacy-Anwendung und deren Daten  
**Bewertungsmaßstab:** tatsächlich vorhandener Code, OpenAPI-Spezifikation, Migrationen
und lokal ausgeführte Qualitätschecks

## 1. Projektüberblick

### Projekt

- Anzeigename: **CC CRM**
- Python-Package: `cc_crm`
- technischer Projektordner: `cc-crm`
- API-Version: `0.1.0`

### Backend-Stack

- Python 3.13 in einer projektlokalen `.venv`
- FastAPI und Pydantic 2
- SQLAlchemy 2
- Alembic
- PostgreSQL als Zielsystem, SQLite nur für lokale Entwicklung und Tests
- pytest, Ruff und mypy

### Frontend-Stack

- Next.js 15.5 mit App Router
- React 19
- TypeScript 5
- Tailwind CSS 4
- lokale shadcn/ui-Struktur mit Radix UI
- lucide-react
- pnpm 11

### Startbefehle

Backend, aus `backend/`:

```powershell
$env:CC_CRM_DATABASE_URL = "sqlite:///./cc_crm_local.db"
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn cc_crm.main:app --app-dir src --reload
```

Frontend, aus `frontend/`:

```powershell
Copy-Item .env.example .env.local
pnpm install
pnpm dev
```

### URLs

| Ziel | URL |
|---|---|
| Frontend | `http://localhost:3000` |
| Swagger | `http://127.0.0.1:8000/docs` |
| Healthcheck | `http://127.0.0.1:8000/api/v1/health` |
| OpenAPI | `http://127.0.0.1:8000/openapi.json` |

## 2. Ordnerstruktur

```text
cc-crm/
├── backend/
│   ├── alembic/
│   │   └── versions/
│   │       ├── 779af1589185_create_core_crm_tables.py
│   │       ├── 411de3299065_add_recruiting_process_entities.py
│   │       └── 5c1c4f821b90_add_operational_crm_fields.py
│   ├── src/cc_crm/
│   │   ├── api/v1/
│   │   ├── core/
│   │   ├── infrastructure/database/
│   │   ├── integrations/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   └── services/
│   ├── tests/api/
│   ├── alembic.ini
│   └── pyproject.toml
├── frontend/
│   ├── public/brand/
│   │   ├── commandeur-logo.png
│   │   └── commandeur-brand.jpg
│   ├── src/app/
│   ├── src/components/crm/
│   ├── src/components/layout/
│   ├── src/components/ui/
│   ├── src/lib/api/
│   ├── src/lib/demo-data.ts
│   └── package.json
└── docs/
    ├── ARCHITECTURE_REPORT.md
    ├── REFACTORING_PLAN.md
    └── CC_CRM_AUDIT_REPORT.md
```

### Legacy, ausdrücklich nicht auditiert

Die frühere Streamlit-/SQLite-Anwendung wurde nach dem Audit aus dem aktiven
Projektstamm entfernt. Ihre Dateien liegen ausschließlich im lokalen, per
`.gitignore` ausgeschlossenen Ordner `_cleanup_backup_legacy/`. Dieser
Backup-Ordner ist kein Bestandteil des neuen CC CRM und soll nicht nach GitHub
übertragen werden.

## 3. Backend-Architektur

### Packages

| Bereich | Aufgabe |
|---|---|
| `api/v1` | HTTP-Routen, Request-Parameter und Response-Modelle |
| `schemas` | Pydantic-Create-, Update-, Read- und Prozessschemas |
| `services` | Business-Regeln, Transaktionen und Orchestrierung |
| `repositories` | SQLAlchemy-Abfragen und Persistenz |
| `models` | relationale SQLAlchemy-Modelle |
| `core` | Konfiguration, Fehlerklassen |
| `infrastructure/database` | Engine und Session-Lifecycle |
| `integrations` | providerbezogene Adapter-Grenzen |
| `alembic/versions` | versionierte DDL-Migrationen |

Der vorgesehene Datenfluss ist erkennbar und überwiegend eingehalten:

```text
API Router → Service → Repository → SQLAlchemy Model → Datenbank
```

CRUD-Routen enthalten kaum Fachlogik. Statuswechsel, Gebührenberechnung,
Duplikatsprüfung und Folgeobjekte liegen in Services. Eine Ausnahme ist das
Zusammenstellen von Response-Seiten in einzelnen Routern; das ist Präsentations-,
nicht Geschäftslogik.

Integrationsordner sind für `ai`, `bullhorn`, `calendar`, `gmail`, `linkedin`,
`microsoft_graph` und `webhooks` vorhanden. Bis auf Modul-Platzhalter sind dort
noch keine Providerimplementierungen vorhanden.

## 4. Datenmodell

| Modell / Tabelle | Wichtigste Felder und Beziehungen | Fachlicher Zweck |
|---|---|---|
| `Candidate` / `candidates` | Nummer, Name, Kontakt, Rolle, Qualifikation, PLZ/Ort, Gehalt, Kündigungsfrist, Verfügbarkeit, CV, Kurzprofil, Einwilligung, Status | Talentprofil |
| `ClientCompany` / `client_companies` | Name, Status, Kontakt, Adresse, Region, Größe, Fokus, AGB-Status, Honorar, Rückzahlung, Garantie, Zahlungsziel | Kanzlei-/Kundenprofil |
| `ContactPerson` / `contact_persons` | FK Kanzlei, Name, Rolle, E-Mail, Telefon, primär | Ansprechpartner einer Kanzlei |
| `JobMandate` / `job_mandates` | FK Kanzlei, Titel, Status, Ort, Radius, Arbeitsmodell, Qualifikationen, Erfahrung, Gehaltsrahmen, Honorar | optionaler Suchauftrag |
| `CandidateSubmission` / `candidate_submissions` | FK Kandidat, Kanzlei, optional Mandat und Kontakt; Status, Versanddaten, Kurzprofil, Gehalt, Fee, Feedback, Follow-up, Owner | zentrales CV-Out-Objekt |
| `SubmissionFeedback` / `submission_feedback` | FK Submission, Typ, Text, Datum, nächster Schritt | Kunden-/Kandidatenfeedback |
| `Interview` / `interviews` | FK Submission, Termin, Typ, Ort/Link, Teilnehmer, Status | Interviewereignis |
| `Offer` / `offers` | FK Submission, Gehalt, variable Vergütung, Start, Status | Angebot |
| `Placement` / `placements` | eindeutiger FK Submission, Start, finales Gehalt, Honorarprozentsatz, berechnete Fee, Garantie | erfolgreiche Besetzung |
| `Fee` / `fees` | FK Placement, netto, USt., brutto, Rechnungsstatus und Fälligkeit | Rechnung/Zahlung |
| `Task` / `tasks` | optionale FK zu Kandidat, Kanzlei und Submission, Fälligkeit, Status, Priorität | Aufgabe/Follow-up |
| `Note` / `notes` | optionale FK zu Kandidat, Kanzlei und Submission, Text | Freitextnotiz |
| `Activity` / `activities` | optionale FK zu Kandidat, Kanzlei und Submission, Typ, Betreff, Details, Zeitpunkt | fachliche Chronik |
| `AuditLog` / `audit_logs` | Entität, ID, Aktion, Zeitpunkt, Benutzer, alte/neue Werte | technischer Audit Trail |
| `Document` / `documents` | Owner-Typ/-ID, Dokumenttyp, Dateiname, Storage-Key, MIME, Größe, optional Versand-Submission | Dokumentmetadaten |
| `SourcingMetric` / `sourcing_metrics` | Zeitraum, Quelle, Kampagne, Pitches, Antworten, positive Antworten, Quali Calls | manuelle Sourcing-KPIs |
| `EmailDraftLog` / `email_draft_logs` | Template, optionale FK, Empfänger, Betreff, Text, Provider, externe Draft-ID | Outlook-Entwurfsprotokoll |

### CandidateSubmission-Verknüpfung

`CandidateSubmission` enthält zwingende Fremdschlüssel auf `Candidate` und
`ClientCompany`. `JobMandate` und `ContactPerson` sind optional. Der Service
prüft, dass ein angegebenes Mandat bzw. ein Kontakt zur gewählten Kanzlei gehört.

CV-Outs werden beim Kandidaten über
`GET /candidates/{candidate_id}/submissions` sichtbar. Kanzleibezogene CV-Outs
werden über `GET /submissions?client_id=...` geliefert. Das Kanzleidetail im
Frontend filtert derzeit eine bereits geladene Submission-Liste clientseitig.

### Fee-Berechnung

Bei der Placement-Erstellung:

```text
calculated_fee = final_salary × fee_percentage / 100
```

Das Ergebnis wird kaufmännisch auf zwei Nachkommastellen gerundet. Beim Anlegen
einer Fee wird Brutto aus Netto plus USt. berechnet. Standard-USt. ist 19 %.

**Audit-Hinweis:** Der Kanzlei-Standard von 27 % wird gespeichert, aber bei der
Placement-Erstellung nicht automatisch übernommen. `PlacementCreate` verlangt
den Prozentsatz explizit. Damit ist die 27-%-Logik fachlich nur teilweise
durchgängig umgesetzt.

### Rückzahlung und Garantie

`ClientCompany.refund_terms` speichert standardmäßig:

```text
50 % vor Antritt; 50 % im ersten Monat; 25 % im zweiten Monat
```

Der Text ist pro Kanzlei überschreibbar und kann zusätzlich auf dem CV-Out
gespeichert werden. Es handelt sich um Freitext, nicht um strukturierte
Rückzahlungsstufen. `guarantee_period_months` ist separat numerisch gespeichert.

## 5. Statusautomaten und Business-Logik

### Submission-Statuswerte

`draft`, `sent`, `client_review`, `feedback_pending`,
`interview_requested`, `interview_scheduled`, `offer_expected`,
`offer_received`, `placed`, `rejected`, `withdrawn`, `cancelled`.

### Erlaubte Übergänge

| Von | Nach |
|---|---|
| `draft` | `sent`, `cancelled` |
| `sent` | `client_review`, `rejected`, `withdrawn` |
| `client_review` | `feedback_pending`, `interview_requested`, `rejected`, `withdrawn` |
| `feedback_pending` | `interview_requested`, `rejected`, `withdrawn` |
| `interview_requested` | `interview_scheduled`, `rejected`, `withdrawn` |
| `interview_scheduled` | `offer_expected`, `rejected`, `withdrawn` |
| `offer_expected` | `offer_received`, `rejected`, `withdrawn` |
| `offer_received` | `placed`, `rejected`, `withdrawn` |

Alle nicht aufgelisteten Übergänge sind verboten und erzeugen einen
`BusinessRuleError`. Endzustände besitzen keine ausgehenden Übergänge.

### Automatische Nebenwirkungen

- Submission-Erstellung erzeugt eine Activity.
- Jeder Statuswechsel erzeugt Activity und AuditLog mit Alt-/Neustatus.
- Feedback, Interview, Offer, Placement und Fee erzeugen Activities.
- Diese Prozessobjekte erzeugen außerdem AuditLogs.
- Interview-, Offer- und Placement-Erstellung können den Statusautomaten
  automatisch weiterschalten.

### Follow-up-Regeln

| Regel | Stand | Audit-Bewertung |
|---|---|---|
| `sent` → +3 Tage | `follow_up_at` und verknüpfte High-Priority-Task | vollständig |
| `interview_scheduled` → +1 Tag | Task wird einen Tag nach Statuswechsel fällig | teilweise: nicht einen Tag nach tatsächlichem Interviewtermin |
| `offer_received` → +1 Tag | Task und `follow_up_at` | vollständig |
| `placed` → +1 Tag | Task „Placement und Rechnung nachverfolgen“ | vollständig |

Tasks tragen Kandidat-, Kanzlei- und Submission-ID. Sie sind damit nicht lose.

## 6. API-Endpunkte

Statuslegende: **fertig** = persistente Funktion vorhanden; **teilweise** =
technisch vorhanden, aber fachlicher End-to-End-Flow fehlt; **Platzhalter** =
nur vorbereitende Struktur.

| Methode | Pfad | Zweck | Request → Response | Status |
|---|---|---|---|---|
| GET | `/api/v1/health` | Healthcheck | – → Health-Payload | fertig |
| GET/POST | `/api/v1/candidates` | Liste/Anlage | CandidateCreate → Page/CandidateRead | fertig |
| GET/PATCH/DELETE | `/api/v1/candidates/{id}` | Detail/Pflege/Löschen | CandidateUpdate → CandidateRead | fertig |
| GET | `/api/v1/candidates/{id}/submissions` | CV-Outs eines Kandidaten | Query → Liste | fertig |
| POST | `/api/v1/candidates/{id}/profile-suggestion` | Kurzprofilvorschlag | – → ProfileSuggestion | teilweise |
| GET/POST | `/api/v1/clients` | Kanzleiliste/Anlage | ClientCreate → Page/ClientRead | fertig |
| GET/PATCH/DELETE | `/api/v1/clients/{id}` | Kanzleidetail/Pflege/Löschen | ClientUpdate → ClientRead | fertig |
| GET/POST | `/api/v1/contacts` | Kontakte | ContactCreate → Liste/ContactRead | fertig |
| GET/PATCH/DELETE | `/api/v1/contacts/{id}` | Kontakt-CRUD | ContactUpdate → ContactRead | fertig |
| GET/POST | `/api/v1/jobs` | Mandate | JobCreate → Page/JobRead | fertig |
| GET/PATCH/DELETE | `/api/v1/jobs/{id}` | Mandat-CRUD | JobUpdate → JobRead | fertig |
| GET/POST | `/api/v1/submissions` | filtern/anlegen | SubmissionCreate → Page/SubmissionRead | fertig |
| GET/PATCH/DELETE | `/api/v1/submissions/{id}` | CV-Out-CRUD | SubmissionUpdate → SubmissionRead | fertig |
| PATCH | `/api/v1/submissions/{id}/transition` | Statuswechsel | SubmissionTransition → SubmissionRead | fertig |
| GET/POST | `/api/v1/submissions/{id}/feedback` | Prozessfeedback | FeedbackCreate → Liste/FeedbackRead | fertig |
| GET/POST | `/api/v1/submissions/{id}/interviews` | Interviews | InterviewCreate → Liste/InterviewRead | fertig |
| GET/POST | `/api/v1/submissions/{id}/offers` | Offers | OfferCreate → Liste/OfferRead | fertig |
| GET/POST | `/api/v1/submissions/{id}/placement` | Placement | PlacementCreate → PlacementRead | fertig |
| GET | `/api/v1/feedback` | globales Feedback | Query → Liste | fertig |
| GET | `/api/v1/interviews` | globale Interviews | – → Liste | fertig |
| GET | `/api/v1/offers` | globale Offers | – → Liste | fertig |
| GET | `/api/v1/placements` | globale Placements | – → Liste | fertig |
| GET | `/api/v1/fees` | Fees | – → Liste | fertig |
| POST | `/api/v1/placements/{id}/fees` | Fee/Rechnung anlegen | FeeCreate → FeeRead | fertig |
| GET/POST | `/api/v1/tasks` | Aufgaben | TaskCreate → Liste/TaskRead | fertig |
| GET/PATCH/DELETE | `/api/v1/tasks/{id}` | Aufgaben-CRUD | TaskUpdate → TaskRead | fertig |
| GET/POST | `/api/v1/notes` | Notizen | NoteCreate → Liste/NoteRead | fertig |
| GET/PATCH/DELETE | `/api/v1/notes/{id}` | Notiz-CRUD | NoteUpdate → NoteRead | fertig |
| GET/POST | `/api/v1/activities` | Activities | ActivityCreate → Liste/ActivityRead | fertig |
| GET/PATCH/DELETE | `/api/v1/activities/{id}` | Activity-CRUD | ActivityUpdate → ActivityRead | fertig |
| GET | `/api/v1/audit-logs` | Audit Trail | – → Liste | fertig |
| GET | `/api/v1/cockpit` | Follow-ups/KPIs/Quoten | `period` → CockpitRead | teilweise |
| GET/POST | `/api/v1/documents` | Dokumentmetadaten | DocumentCreate → Liste/DocumentRead | teilweise |
| GET/POST | `/api/v1/sourcing-metrics` | manuelle Sourcing-KPIs | SourcingMetricCreate → Liste/Read | fertig |
| GET | `/api/v1/email-templates` | Templatekatalog | – → EmailTemplateRead[] | teilweise |
| POST | `/api/v1/email-drafts` | Draft protokollieren | EmailDraftCreate → EmailDraftRead | teilweise |

Listen-, Detail- und Mutationsendpunkte für Activities, Notes, Tasks, Contacts,
Jobs, Candidates und Clients sind als einzelne OpenAPI-Operationen vorhanden.
Der Report fasst gleichartige CRUD-Operationen zusammen, ohne sie auszulassen.

## 7. Frontend-Architektur

- Next.js App Router unter `frontend/src/app`.
- Globales Layout bindet `AppShell` ein.
- `AppShell` verwaltet responsive Sidebar und Topbar.
- Sidebar-Navigation stammt aus `components/layout/navigation.ts`.
- UI-Bausteine liegen lokal in `components/ui`.
- CRM-Komponenten liegen in `components/crm`.
- API-Client: `src/lib/api/client.ts`.
- API-Typen: `src/lib/api/types.ts`.
- Query-Funktionen: `src/lib/api/queries.ts`.
- Demo-Daten: `src/lib/demo-data.ts`.

### Echte API vs. Demo

`NEXT_PUBLIC_CC_CRM_API_URL` definiert die zentrale Base-URL. Ist sie nicht
gesetzt oder schlägt ein Request fehl, liefert `apiGet` die je Query
übergebenen Demo-Daten. Eine `.env.local` existiert aktuell nicht; daher läuft
der derzeitige lokale Produktionsbuild mit Demo-Fallbacks.

In Komponenten sind keine Backend-URLs hardcodiert. Lokale URLs stehen nur in
README und `.env.example`.

### Zustände

- globales `loading.tsx` mit Skeletons vorhanden
- globales `error.tsx` mit Retry vorhanden
- mehrere fachliche Empty States vorhanden
- Demo-Modus wird sichtbar durch `DemoNotice` gekennzeichnet
- Form-Mutationen besitzen noch keine durchgängigen Loading-/Success-/Error-Flows

## 8. Frontend-Seiten und Funktionen

| Route | Zweck/UI | Datenanbindung | Lücken |
|---|---|---|---|
| `/` | Follow-ups, heiße Prozesse, KPIs, Quoten | Cockpit-API mit Demo-Fallback | Zeitraumbuttons ohne Interaktion; Quali Calls nicht aus Sourcing aggregiert |
| `/kandidaten` | Kandidatentabelle, Suche/Filter-UI, Status, Dokumentindikatoren | API mit Demo-Fallback | Suche/Filter und „Anlegen“ ohne Aktion |
| `/kandidaten/[id]` | Übersicht, Kurzprofil, CV-Outs und weitere Tabs | Candidate/Clients/Submissions API mit Fallback | Kurzprofil-Buttons speichern/erzeugen nicht; mehrere Tabs Platzhalter |
| `/kanzleien` | Kanzleiliste mit AGB/Honorar | API mit Demo-Fallback | Suche/Filter und Anlage ohne Aktion |
| `/kanzleien/[id]` | Übersicht, Kandidaten, Konditionen, Dokumente | Listen-APIs, clientseitig gefiltert | kein direkter Client-Detailquery; Dokumenttab ohne Upload |
| `/cv-outs` | Kanban und Tabelle | Submissions/Candidates/Clients API mit Fallback | Filter und Anlage ohne Aktion; kein Drag-and-drop/Statuswechsel |
| `/mandate` | Mandatskarten und Matching-Hinweis | statische Demo-Daten | kein API-Query, kein Matching-Service |
| `/interviews` | Navigationsziel | keine | Platzhalter |
| `/offers` | Navigationsziel | keine | Platzhalter |
| `/placements` | Navigationsziel | keine | Platzhalter |
| `/fees` | Navigationsziel | keine | Platzhalter |
| `/aufgaben` | Follow-up-Karten | ausschließlich `demoCockpit` | Task-API nicht angebunden |
| `/aktivitaeten` | Navigationsziel | keine | Platzhalter |
| `/einstellungen` | Navigationsziel | keine | Platzhalter |
| `/sourcing` | KPI-Karten/Kampagne | statische Werte | Sourcing-API nicht angebunden; Erfassung ohne Aktion |
| `/outlook` | Templatekarten und Sicherheitswarnung | Template-API mit Demo-Fallback | Buttons erzeugen keinen Draft; kein Graph |

## 9. Dashboard-/Cockpit-Prüfung

### Umgesetzt

- Fällige/überfällige Aufgaben stehen oben links.
- Heiße Interview-/Offer-/Placement-Prozesse stehen oben rechts.
- KPI-Karten folgen darunter.
- vier Funnelquoten werden darunter angezeigt.
- Backend-Cockpit aggregiert Tasks, Submissions, Interviews, Offers,
  Placements und Fees.

### Nur vorbereitet oder unvollständig

- Zeitraum wird vom Backend für Woche/Monat/Quartal akzeptiert.
- Frontend zeigt Zeitraumbuttons, übergibt aber fest `week`.
- Benutzerdefinierter Zeitraum fehlt.
- `qualification_calls` ist im Cockpit-Service fest `0`.
- `cv_available` ist ein Gesamtbestand, nicht periodenbezogen.
- erwartete Fees summieren alle Submissions statt nur den gewählten Zeitraum.
- Follow-up- und Hot-Process-Details enthalten IDs, aber keine serverseitig
  aufgelösten Kandidaten-/Kanzleinamen.

Aktuell zeigt der lokale Build Demo-Cockpitdaten, weil keine `.env.local`
konfiguriert ist.

## 10. Dokumente, Dateien und Logo

- `Document` und `DocumentCreate/Read` existieren.
- Owner-Typen: Candidate, Client, Submission, Placement, Fee.
- Dokumenttypen sind freier validierter Text, keine Enum.
- Es werden Dateiname, Storage-Key, MIME, Größe und Versandbezug gespeichert.
- Es gibt **keinen binären Upload**, keinen Storage-Adapter, keinen Download,
  keinen Virenscan und keine Zugriffskontrolle.
- Kandidaten-/Kanzleidokumenttabs sind UI-Platzhalter.

Das Logo ist real eingebunden:

- Asset: `frontend/public/brand/commandeur-logo.png`
- Komponente: `frontend/src/components/layout/sidebar.tsx`
- Nutzung: Next.js `Image`, Alt-Text „Commandeur Consulting“

Ein Austausch ist durch Ersetzen der Datei unter gleichem Namen möglich.

## 11. Outlook-/E-Mail-Workflows

### Vorhanden

- `EmailDraftLog` als persistentes Modell
- Templatekatalog im `EmailWorkflowService`
- Platzhalterliste
- API für Templates und Draft-Log
- Frontendseite mit Templatekarten
- klarer Hinweis, dass nichts automatisch versendet wird

Templates sind vorgesehen für Kandidatenvorstellung, CV-Anforderung,
Kurzprofilfreigabe, CV-Out-Follow-up, Interviewbestätigung,
Interviewfeedback, Offer, Kandidaten-/Kundenabsage, AGB und Placement/Rechnung.

### Nicht umgesetzt

- kein eigenes `EmailTemplate`-Datenbankmodell; Templates sind Codekonstanten
- keine Platzhalter-Rendering-/Validierungsengine
- keine Microsoft-Graph-Authentifizierung
- kein realer Outlook-Draft
- kein Senden
- Frontendbutton ruft `POST /email-drafts` nicht auf
- Anlagen werden keinem Draft physisch beigefügt

Bewertung: **technische Vorbereitung, kein produktiver Outlook-Workflow**.

## 12. KI-Kurzprofil

- Feld `Candidate.short_profile` vorhanden.
- API `POST /candidates/{id}/profile-suggestion` vorhanden.
- UI-Aktion „Kurzprofil erzeugen“ und editierbares Textfeld vorhanden.
- Service erzeugt deterministischen Text aus Kandidatenfeldern.
- `integrations/ai` existiert nur als Paketgrenze.

Nicht vorhanden:

- keine LLM-/KI-Anbindung
- UI-Button ruft API nicht auf
- „Speichern“ ruft Candidate-Patch nicht auf
- keine Versionierung/Freigabe
- CV-Out und Outlook können Textfelder aufnehmen, nutzen das gespeicherte
  Kurzprofil aber nicht automatisch

Bewertung: **Datenstruktur und UX vorbereitet, echte KI und End-to-End-Speicherung fehlen**.

## 13. Mandat-Matching und Umkreissuche

Vorhandene Felder: Mandatsort, `search_radius_km` mit Standard 30,
Arbeitsmodell, Qualifikationen, Erfahrung, Gehaltsrahmen. Kandidaten besitzen
PLZ, Ort, Rolle, Qualifikation, Gehalt und Kündigungsfrist.

Frontend zeigt Beispielmandate und statische Match-Anzahlen.

Nicht vorhanden:

- keine Koordinaten
- kein Geocoding
- keine Distanzberechnung
- kein Matching-Endpunkt
- kein gewichteter Score
- keine echten Kandidatenvorschläge

Bewertung: **Datenmodell vorbereitet, Matchingfunktion fehlt**.

## 14. KPI, LinkedIn und Sourcing

`SourcingMetric` und GET/POST-Endpunkte unterstützen:

- Pitches/InMails
- Antworten
- positive Antworten
- Quali Calls
- Start/Ende
- Quelle und optionale Kampagne

Cockpit-Zeiträume: Woche, Monat, Quartal. Ein benutzerdefinierter Zeitraum fehlt.
Die Sourcingseite verwendet noch statische Werte und keine API.

Berechnete Quoten:

- CV-Out → Interview
- Interview → Offer
- Offer → Placement
- Placement → bezahlt

Fehlende Quoten:

- Pitch → Antwort
- Antwort → Quali Call
- Quali Call → CV In
- CV In → CV-Out
- positive Antwortquote

## 15. Tests und Qualität

### Tatsächlich ausgeführte Backend-Checks

| Check | Ergebnis |
|---|---|
| pytest | **9 bestanden** |
| Ruff | **bestanden**, keine Findings |
| mypy | **bestanden**, 84 Source-Dateien |
| Alembic Upgrade → Head | bestanden |
| Alembic Downgrade → Base | bestanden |
| Alembic Upgrade → Head | bestanden |

Der Migrationstest lief gegen die separate Datei
`backend/audit_migration_roundtrip.db`. Sie wurde danach entfernt. Die lokale
CRM-Datenbank wurde nicht für den Downgrade verwendet.

Warnung: Starlette meldet eine Deprecation für `httpx` im `TestClient` und
empfiehlt künftig `httpx2`. Das ist aktuell kein Testfehler.

### Tatsächlich ausgeführte Frontend-Checks

| Check | Ergebnis |
|---|---|
| `pnpm lint` | bestanden |
| `pnpm build` | bestanden, 17 App-Routen |
| `pnpm dev` auf Port 3001 | HTTP 200 |

Bekannte Testlücken:

- keine Frontend-Komponenten-/E2E-Tests
- keine PostgreSQL-Migration im CI geprüft
- keine Tests für Dokumente, Sourcing CRUD, Draft-Erstellung und alle
  Follow-up-Zeitpunkte
- kein Last-/Volumentest für 100.000+ Kandidaten

## 16. Sicherheits- und Datenrisiken

| Risiko | Bewertung |
|---|---|
| Authentifizierung | fehlt vollständig |
| Rollen/Berechtigungen | fehlen vollständig |
| personenbezogene Daten | keine Zugriffspolitik, Löschfristen oder DSAR-Prozesse |
| Uploads | noch nicht implementiert; vor Umsetzung Scan, Größenlimit, MIME-Prüfung und private Storage-URLs nötig |
| Secrets | keine echten Secrets gefunden; Beispielkennwort `change-me` nur Konfigurationsdefault |
| lokale Pfade | Backend-README enthält einen benutzerspezifischen Python-Pfad; nicht portabel |
| CORS | konfigurierbar; Default ist leer, Beispiel erlaubt nur `localhost:3000`; Credentials aktiviert |
| Audit Trail | für Status und Prozessobjekte vorhanden, nicht für alle CRUD-Änderungen |
| Datenvalidierung | Pydantic vorhanden; freie Status-/Dokumenttyptexte teilweise zu locker |
| Testdaten | neue Tests nutzen generische Musterdaten; Demo-Frontend nutzt fiktive `.test`-Adressen |
| Mandantentrennung | fehlt |
| Verschlüsselung/Backup | nicht in Anwendungsebene dokumentiert |
| Draft-/Mail-Sicherheit | kein Versand, daher aktuell kein Send-Risiko; später explizite Freigabe nötig |

Das System ist ohne Authentifizierung und Berechtigungskonzept **nicht
produktionsreif für echte Kandidatendaten**.

## 17. Fachliche Bewertung gegen Soll-Prozess

| Schritt | Status | Begründung |
|---|---|---|
| 1. Kandidat anlegen | vollständig umgesetzt | API CRUD; Frontend-Button noch ohne Formular |
| 2. Quali Call/Status pflegen | teilweise | Kandidatenstatus vorhanden; Quali Call nicht als eigenes Ereignis |
| 3. CV/Kurzprofil | teilweise | Felder und Vorschlag vorhanden, UI nicht verdrahtet |
| 4. Kandidat vorstellen | vollständig im Backend | Submission ist Kernobjekt; Frontend-Anlage ohne Aktion |
| 5. CV-Out → Follow-up +3 | vollständig im Backend | Task und Follow-up pro Submission |
| 6. Feedback erfassen | vollständig im Backend | API/Modell; Frontend fehlt |
| 7. Interview planen | vollständig im Backend | API/Modell/Statuswechsel; Frontendseite Platzhalter |
| 8. Interviewfeedback +1 | teilweise | +1 ab Statuswechsel, nicht ab Interviewtermin |
| 9. Offer erfassen | vollständig im Backend | API/Modell/Statuswechsel; Frontendseite Platzhalter |
| 10. Offer-Follow-up +1 | vollständig im Backend | Task und Follow-up |
| 11. Placement erfassen | vollständig im Backend | API/Modell; Frontendseite Platzhalter |
| 12. Fee berechnen | vollständig mit Einschränkung | Berechnung korrekt; 27 % nicht automatisch aus Kanzlei |
| 13. Rechnung/Zahlung | teilweise | Fee-Statusmodell/API vorhanden, keine Update-Route/Frontend |
| 14. KPIs/Quoten | teilweise | vier Quoten; Periodenlogik und Sourcing-Funnel unvollständig |
| 15. LinkedIn-Zahlen erfassen | Backend vollständig, Frontend vorbereitet | Modell/API vorhanden, UI statisch |

## 18. Priorisierte To-do-Liste

### Prio 1: Muss als Nächstes

1. Authentifizierung, Benutzer, Rollen und objektbezogene Berechtigungen vor
   Nutzung echter personenbezogener Daten implementieren.
2. Frontend-Mutationen für Kandidaten, Kanzleien, CV-Outs, Tasks, Feedback,
   Interviews, Offers, Placements und Fees an bestehende API anbinden.
3. `.env.local` sauber konfigurieren und Demo-/API-Modus explizit steuerbar
   machen; Demo-Fallback darf produktive API-Fehler nicht verdecken.
4. Interview-Follow-up auf `scheduled_at + 1 Tag` korrigieren und testen.
5. 27-%-Kanzleihonorar bei Placement/CV-Out als Default übernehmen und
   Überschreibungen nachvollziehbar auditieren.
6. Fee-Patch-/Rechnungsstatus-Endpunkt und UI für „issued/due/paid“ ergänzen.

### Prio 2: Wichtig, aber nicht sofort

1. Sicheres Dokument-Storage mit Upload/Download, Malwareprüfung, Limits,
   Berechtigungen und Löschkonzept bauen.
2. Outlook/Graph-Adapter mit OAuth, expliziter Entwurfsfreigabe,
   Platzhalterrendering und Anlagen implementieren.
3. Kandidaten-/Kanzlei-/Submission-Detailendpunkte erstellen, um große
   Gesamtabfragen im Frontend zu vermeiden.
4. Cockpit-Zeitraumfilter vollständig machen und Sourcing-KPIs integrieren.
5. E2E-Tests für den kompletten Recruiting-Prozess ergänzen.
6. PostgreSQL-CI und Volumentests für geplante Datenmengen einführen.

### Prio 3: Später / Nice-to-have

1. Geocoding, Radiusabfrage und gewichtetes Mandatsmatching.
2. LLM-Adapter für Kurzprofile mit Promptversionierung und Human Approval.
3. LinkedIn-/Bullhorn-/Kalenderadapter.
4. konfigurierbare Templates und Follow-up-Regeln im Einstellungsbereich.
5. BI-/Exportfunktionen und Kampagnenvergleich.

## 19. Reviewer-Hinweise

### Zuerst anzusehende Dateien

1. `backend/src/cc_crm/services/submissions.py`
2. `backend/src/cc_crm/services/recruiting.py`
3. `backend/src/cc_crm/services/operational.py`
4. `backend/src/cc_crm/models/submission.py`
5. `frontend/src/lib/api/client.ts`

### Zuerst zu testende API-Endpunkte

1. `PATCH /api/v1/submissions/{id}/transition`
2. `POST /api/v1/submissions/{id}/placement`
3. `POST /api/v1/placements/{id}/fees`
4. `GET /api/v1/cockpit?period=week`
5. `POST /api/v1/candidates/{id}/profile-suggestion`

### Zuerst zu öffnende Frontend-Seiten

1. `/`
2. `/kandidaten`
3. `/kandidaten/{id}`
4. `/cv-outs`
5. `/kanzleien/{id}`

## Gesamturteil

CC CRM besitzt eine gute API-first-Grundstruktur und ein fachlich richtiges
CandidateSubmission-Kernobjekt. Der Backend-Prozess von CV-Out über Interview,
Offer, Placement und Fee ist substanziell vorhanden und getestet. Das Frontend
vermittelt bereits das Zielbild eines operativen Recruiting-Cockpits, ist aber
in mehreren Bereichen noch eine lesende Demo bzw. ein UI-Platzhalter.

Für einen internen Prototyp ist der Stand belastbar. Für den produktiven Einsatz
mit echten Kandidaten- und Kundendaten fehlen insbesondere Authentifizierung,
Berechtigungen, sichere Dokumentablage, vollständig angebundene Frontend-
Mutationen und die reale Outlook-Integration.
