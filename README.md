# CC CRM

API-first Recruiting-CRM für Commandeur Consulting.

## Struktur

- `backend/`: FastAPI, SQLAlchemy, Alembic und PostgreSQL-Zielarchitektur
- `frontend/`: Next.js, TypeScript, Tailwind CSS und shadcn/ui
- `docs/`: Architektur-, Audit- und Projektdokumentation
- `_cleanup_backup_legacy/`: lokales Backup des entfernten Prototyps

## Backend starten

```powershell
cd backend
$env:CC_CRM_DATABASE_URL = "sqlite:///./cc_crm_local.db"
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn cc_crm.main:app --app-dir src --reload
```

Swagger: `http://127.0.0.1:8000/docs`

## Frontend starten

```powershell
cd frontend
Copy-Item .env.example .env.local
pnpm install
pnpm dev
```

Frontend: `http://localhost:3000`

Ausführliche Hinweise stehen in `backend/README.md`, `frontend/README.md` und
`docs/CC_CRM_AUDIT_REPORT.md`.
