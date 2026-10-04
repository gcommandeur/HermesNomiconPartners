# Hinweise für Claude Code — Hermes CRM (cc-crm)

## Projektpfad (Stand 2026-09-17)

**Dieses Projekt liegt unter `C:\Users\comma\HermesCRM`.**

Frühere Pfade sind **tot** und dürfen nicht mehr verwendet werden:

- `C:\Users\comma\OneDrive - Commandeur Consulting GmbH\Desktop\HermesCRM` — am 2026-09-17 hierher verschoben und gelöscht
- `C:\Users\comma\Documents\Codex\2026-06-07\cc-crm` — bereits 2026-07-09 vom Nutzer gelöscht

Falls in älteren Notizen, Chats oder Konfigurationen einer dieser Pfade auftaucht: als nicht existent behandeln.

**Das Projekt darf nicht zurück in einen OneDrive-synchronisierten Ordner.** Grund für den Umzug: Der Desktop läuft über OneDrive Known Folder Move, dadurch ließen sich `node_modules`, `.venv` und `.git` nicht von der Synchronisierung ausnehmen. Rund 12,4 GB mit zehntausenden ständig wechselnden Dateien erzeugten permanente Sync-Last und Cloud-Platzhalter-Fehler (Fehler 395 / `0x0000018B`) beim Dateizugriff.

## Umgebung und Fallstricke

**pnpm in PowerShell:** Die PowerShell-ExecutionPolicy dieses Systems blockiert `.ps1`-Skripte, deshalb schlagen `npm` und `pnpm` dort mit `CommandNotFoundException` bzw. `UnauthorizedAccess` fehl. Zuverlässiger Weg daran vorbei:

```powershell
corepack pnpm install
corepack pnpm dev
```

In Git Bash oder cmd greift die Policy nicht, dort funktioniert `pnpm` direkt. Node ist v24.18.0, Corepack 0.35.0, pnpm 11.7.0.

**Python-venv:** `backend\.venv` wurde am 2026-09-17 am neuen Ort frisch erstellt (Python 3.13.1 aus `C:\Users\comma\AppData\Local\Programs\Python\Python313`), inklusive `pip install -e .` für `cc-crm-api`. Das venv wurde bei früheren Umzügen jeweils mitkopiert und enthielt dann tote absolute Pfade — bei künftigen Verschiebungen also immer neu bauen statt kopieren.

## Starten

```powershell
# Backend (Port 8000, Swagger unter /docs)
cd backend
$env:CC_CRM_DATABASE_URL = "sqlite:///./cc_crm_local.db"
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn cc_crm.main:app --app-dir src --reload

# Frontend (Port 3000)
cd frontend
corepack pnpm dev
```

## Workflow

Der lokale Rechner ist reine Entwicklungs- und Testumgebung: erst lokal testen, dann nach GitHub pushen (`https://github.com/gcommandeur/hermescrm.git`). **Gearbeitet wird auf dem Branch `entwicklung`, nicht auf `main`** (Details in `docs/PROJEKT_STAND.md`). `main` wird nur per Pull Request aktualisiert, nach grüner CI und Freigabe des Nutzers; von `main` aus läuft die Anwendung über DigitalOcean online. GitHub ist die maßgebliche Quelle — die lokale Kopie braucht keine zusätzliche Sicherung.

Ausführliche Doku: `README.md`, `backend/README.md`, `frontend/README.md`, `docs/CC_CRM_AUDIT_REPORT.md`.

## Architektur (Kurzueberblick fuer neue Sitzungen)

Hermes ist ein Recruiting-CRM fuer Steuer-/Rechts-Kanzleien: Kandidaten, Kanzleien, Kontakte, Prozesse (Pipeline), Vakanzen, Mail, Sourcing, Kalender, Analytics. Live: `https://hermescrm-v9sle.ondigitalocean.app` (DigitalOcean App Platform, Deploy automatisch bei Push auf `main`, Migrationen laufen beim Deploy mit, siehe `docs/DEPLOYMENT.md`). Produktions-DB ist Postgres, lokal und in Tests SQLite.

**Backend** (`backend/`, FastAPI + SQLAlchemy 2 + Alembic, Python >= 3.12):
- Schichten in `backend/src/cc_crm/`: `api/v1/*` (Routen, duenn) -> `services/*` (Geschaeftslogik) -> `repositories/*` (Abfragen) -> `models/*` (SQLAlchemy), Pydantic-Schemas in `schemas/*`. Registriert in `api/v1/router.py` (alle geschuetzten Routen hinter Login).
- Wichtige Fachbereiche: `candidates`, `clients` (Kanzleien), `submissions` + `recruiting` (Prozesse mit Stufen qualification_call -> cv_in -> cv_out -> interview -> offer -> placement, dazu Feedback/Interview/Offer/Placement/Fee), `approvals` + `invoices` (Freigabe-Inbox, Rechnungsstatus), `notes`, `sourcing` (Verzeichnis-/Team-Seiten-Suche mit Umkreis), `geo` (PLZ-Koordinaten, Umkreissuche), `mail_*`, `kpi_scoring`, `operational` (Cockpit/Uebersicht).
- Auth: Login mit Passwort + E-Mail-2FA-Code; `api/dependencies.py` hat `CurrentUser`, `AdminUser` und die Zugriffsgrenzen (siehe unten).
- Tests: `backend/tests/` (pytest, SQLite im Speicher, Fixture `client` = angemeldeter Nicht-Admin). Pruefen mit `ruff check src tests`, `mypy src`, `pytest`.
- Migrationen: `backend/alembic/versions/`, aktueller Head `e1c3d5a7b9f2` (users.ms_oid). Neue Migration immer auf einer KOPIE der lokalen DB per upgrade -> downgrade -> upgrade pruefen.

**Frontend** (`frontend/`, Next.js 15 App Router, TypeScript, Tailwind, pnpm):
- Seiten in `frontend/src/app/*` (z.B. `kandidaten`, `kanzleien`, `prozesse`, `sourcing`, `freigaben`, `geschaeftsfuehrung`, `einstellungen/*`), Komponenten in `src/components/crm/*`, API-Zugriff in `src/lib/api/` (`queries.ts`, `hooks.ts` mit SWR, `types.ts`). Browser-Aufrufe laufen ueber `/api/proxy/...`, das den Login-Cookie serverseitig anhaengt.
- Server-Komponenten laden Daten serverseitig, Client-Komponenten (`"use client"`) per SWR. Plain-Module ohne `"use client"` (z.B. `lib/stage-labels.ts`) sind aus beiden nutzbar.
- Pruefen mit `pnpm lint`, `pnpm typecheck`, `NEXT_PUBLIC_CC_CRM_DEMO_MODE=true pnpm build` (genau das macht die CI).

**CI** (`.github/workflows/ci.yml`): Backend (ruff, mypy, pytest unter Python 3.12) und Frontend (lint, typecheck, build). Nach jedem Push das Ergebnis pruefen (`gh run list`) - die CI-Umgebung hat andere Versionen als lokal (z.B. andere mypy/SQLAlchemy-Typen), ein lokal gruener Lauf garantiert nicht, dass CI gruen ist.

## Rechte-Modell (wichtig, nicht aufweichen)

- Rollen in `User.role`: `member` (nur eigene Prozesse), `team_lead` (eigene + die der Mitarbeiter mit `manager_id` auf ihn), `admin` (alles). Nutzerverwaltung nur Admin.
- **Prozesse und alles daran** (Interviews, Offers, Placements, Feedback, Fees, Rechnungen) sind owner-gescopt ueber `CandidateSubmission.owner_user_id`: `process_owner_scope(user, session)` in `api/dependencies.py` liefert `None` (Admin) oder eine Liste erlaubter Nutzer-IDs. Listen filtern damit; jede Route mit `submission_id`/`placement_id`/`fee_id` im Pfad haengt `SubmissionAccess`/`PlacementAccess`/`FeeAccess` an. Fremd UND nicht existent liefert dasselbe 404 (nicht 403). Neue Routen mit solchen IDs MUESSEN eine dieser Pruefungen bekommen - das erzwingt `tests/api/test_access_guard.py` (ruft alle Operationen mit den IDs eines fremden Prozesses auf und erwartet 404; Ausnahmen nur ueber die kommentierte Liste im Test).
- **Kandidaten und Kanzleien** sind bewusst der gemeinsame Pool der ganzen Agentur, ohne Owner-Scoping. Auch **Kommentare** (Notizen, Feedback) sind fuer alle sichtbar (`GET /candidates/{id}/comments`).
- Freigabe-Inbox (`approvals`): Nicht-Admins loesen fuer neue Kanzlei, Honorar-Aenderung und "Rechnung stellen" eine Anfrage aus, Admins entscheiden unter `/freigaben`.
- Der Audit-Log (`audit_logs`, `services/audit_diff.py`) protokolliert normale Feld-Aenderungen als `updated` mit alt/neu; Ereignisse an Prozessen tragen `changed_by` (E-Mail).

## Arbeitsweise in diesem Projekt

- Jede Aufgabe: umsetzen, testen (Backend + Frontend wie oben), mit ausfuehrlicher deutscher Commit-Nachricht committen, pushen, CI-Ergebnis pruefen. Aufgaben als getrennte Commits.
- Vor jedem Commit `git status` pruefen; nie Zugangsdaten committen (einmal lag ein Datenbank-Passwort in einer Diagnose-Datei). Nicht verfolgte Ordner `.git-korrupt-backup/`, `backend/data/lukas_postfach_import/`, `backend/scripts/full_dry_run_log.txt` gehoeren NICHT ins Repo.
- Dateien im Arbeitsverzeichnis haben teils Windows-Zeilenenden (CRLF); bei Skript-Edits darauf achten.
- Keine Passwoerter eingeben, keine Konten anlegen, keine Aktionen gegen die Produktions-Datenbank ohne ausdrueckliche Freigabe des Nutzers. Skripte gegen Produktion (`backend/scripts/`) laufen immer erst als Dry-Run und nur vom Nutzer selbst.
- Konkrete Tests/Muster zum Abschauen: `tests/api/test_owner_filter.py` (Sichtbarkeit), `tests/api/test_team_lead.py` (Rollen), `tests/api/test_approvals.py` (Freigaben), `tests/api/test_candidate_comments.py` (Timeline/Autoren).

## Cloud-/Handy-Workflow

Der Nutzer arbeitet auch rein vom Handy ueber Claude-Code-Cloud-Sitzungen. Dafuer gilt:
- Es gibt nur zwei Branches (`entwicklung`, `main`, keine weiteren anlegen). Cloud- und Laptop-Sitzungen arbeiten beide auf `entwicklung`, **nie direkt auf `main`** (`main` deployt automatisch nach DigitalOcean; Pushes darauf sind in `.claude/settings.json` gesperrt). Ablauf: `git fetch`, `git pull --rebase origin entwicklung`, `docs/PROJEKT_STAND.md` lesen, umsetzen, Pruefbefehle ausfuehren (`pytest`, `ruff check`, `mypy`, `pnpm lint/typecheck/build`), Protokoll in `docs/PROJEKT_STAND.md` ergaenzen, auf `entwicklung` pushen, CI-Ergebnis abwarten. Den Merge nach `main` (Pull Request `entwicklung` -> `main`) macht eine Sitzung nur auf ausdrueckliche Anweisung des Nutzers.
- `.claude/settings.json` erlaubt die Pruefbefehle und das Pushen von `entwicklung` ohne Rueckfrage; Force-Push, `reset --hard` und `branch -D` sind gesperrt. Der Start-Hook `.claude/hooks/cloud-setup.sh` installiert die Abhaengigkeiten (nur in der Cloud).
- Parallel arbeiten Cloud und Laptop an derselben Stelle: vorher `git fetch` und `origin/main` mergen; bei Migrationen vor dem Commit `alembic heads` pruefen (es darf nur EINEN Head geben).
- Nur am Laptop moeglich: Produktions-Skripte, DigitalOcean-Konsole, Klicktests mit echtem Login.

## Gemeinsamer Projektstand (PFLICHT)

Laptop- und Cloud-Sitzungen sehen die Gespraeche der jeweils anderen NICHT. Der gemeinsame Stand lebt in **`docs/PROJEKT_STAND.md`** (kurz: Regeln, offene Punkte, Entscheidungen, Stolperfallen). Die Historie steht in **`docs/PROTOKOLL.md`** (neueste zuerst), Entscheidungen im Detail in `docs/ENTSCHEIDUNGEN.md`, erledigte Plaene in `docs/ARCHIV_PLAENE.md`.

- **Vor jeder Aufgabe:** `git fetch`, `git pull --rebase origin entwicklung`, dann `docs/PROJEKT_STAND.md` lesen. `docs/PROTOKOLL.md` nur bei Bedarf und nur die ersten ca. 100 Zeilen (die Datei ist gross).
- **Nach jeder Aufgabe, im selben Commit:** neuer Protokoll-Eintrag OBEN in `docs/PROTOKOLL.md` (Datum, Laptop/Cloud, was, Commits, was NICHT geprueft wurde, `Gemeldet:` = was dem Nutzer mitgeteilt wurde); in `docs/PROJEKT_STAND.md` nur offene Punkte und neue Entscheidungen/Stolperfallen pflegen (kurz halten, Ziel unter ca. 12 KB). Ohne aktualisierte Datei ist eine Aufgabe nicht fertig.
- **Lokaler Branch `main` = `entwicklung` (Regel des Nutzers vom 2026-10-04, gilt ohne Rueckfrage):** Nach jeder Aufgabe, nach dem Push auf `entwicklung`, setzt die Sitzung den LOKALEN Branch `main` auf `entwicklung` (`git branch -f main entwicklung`, ohne den Branch auszuchecken). Das ist rein lokal und deployt nichts. **Ausdruecklich NICHT von der Regel gedeckt:** `origin/main` (GitHub, deployt nach DigitalOcean) - dorthin geht weiterhin nur mit dem gruenen Licht des Nutzers per Pull Request.
- Nichts Geheimes eintragen.
