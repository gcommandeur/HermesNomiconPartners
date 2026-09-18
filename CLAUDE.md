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

Der lokale Rechner ist reine Entwicklungs- und Testumgebung: erst lokal testen, dann nach GitHub pushen (`https://github.com/gcommandeur/hermescrm.git`, Branch `main`), von wo aus die Anwendung über DigitalOcean online läuft. GitHub ist die maßgebliche Quelle — die lokale Kopie braucht keine zusätzliche Sicherung.

Ausführliche Doku: `README.md`, `backend/README.md`, `frontend/README.md`, `docs/CC_CRM_AUDIT_REPORT.md`.
