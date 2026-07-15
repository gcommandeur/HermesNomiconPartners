# CC CRM Backend

Backend API for the new CC CRM recruiting platform.

The backend is isolated from the Streamlit/SQLite legacy application. It does
not import, migrate, or modify the legacy database.

## Stack

- Python 3.12+
- FastAPI and Pydantic
- SQLAlchemy 2
- PostgreSQL with psycopg
- Alembic migrations
- pytest, Ruff, and mypy

PostgreSQL is the production target. SQLite is supported only for isolated
local development and automated tests.

## Project-local installation on Windows

Run these commands from the repository root:

```powershell
& "C:\Users\comma\AppData\Local\Programs\Python\Python313\python.exe" `
  -m venv backend\.venv

& backend\.venv\Scripts\python.exe `
  -m pip install -e "backend[dev]"
```

No global Python package installation is required.

## Configuration

All runtime configuration is provided through environment variables. Copy
`.env.example` to `.env` inside `backend/` and replace local credentials.
Never commit `.env`.

Production-style PostgreSQL example:

```env
CC_CRM_ENVIRONMENT=local
CC_CRM_API_PREFIX=/api/v1
CC_CRM_DATABASE_URL=postgresql+psycopg://cc_crm:change-me@localhost:5432/cc_crm
CC_CRM_CORS_ORIGINS=["http://localhost:3000"]
CC_CRM_SQL_ECHO=false
```

Temporary local SQLite configuration:

```powershell
$env:CC_CRM_DATABASE_URL = "sqlite:///./cc_crm_local.db"
```

This creates `backend/cc_crm_local.db`, which is ignored by Git. It is not the
legacy CRM database.

## Database migrations

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
```

Show the current revision:

```powershell
.\.venv\Scripts\python.exe -m alembic -c alembic.ini current
```

Create a future migration after changing models:

```powershell
.\.venv\Scripts\python.exe -m alembic -c alembic.ini revision `
  --autogenerate -m "describe the schema change"
```

Always review generated migrations before applying them.

## Operational recruiting endpoints

- `GET /api/v1/cockpit?period=week`: Follow-ups, hot processes, KPIs and rates
- `POST /api/v1/candidates/{id}/profile-suggestion`: editable profile draft
- `GET/POST /api/v1/documents`: document metadata and ownership
- `GET/POST /api/v1/sourcing-metrics`: manually maintained sourcing KPIs
- `GET /api/v1/email-templates`: Outlook-ready template definitions
- `POST /api/v1/email-drafts`: stores a reviewed draft request for the provider adapter

Email drafts are never sent automatically. The Microsoft Graph adapter remains
isolated under `integrations/microsoft_graph`.

## Start the API

From `backend/` after applying migrations:

```powershell
.\.venv\Scripts\python.exe -m uvicorn cc_crm.main:app `
  --app-dir src `
  --host 127.0.0.1 `
  --port 8000 `
  --reload
```

Then open:

- API health: `http://127.0.0.1:8000/api/v1/health`
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

## Tests and quality checks

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests alembic
.\.venv\Scripts\python.exe -m mypy src
```

Tests use a separate SQLite in-memory database and cannot access the legacy
SQLite file.

## Current domain model

- `Candidate`
- `ClientCompany`
- `ContactPerson`
- `JobMandate`
- `CandidateSubmission`
- `SubmissionFeedback`
- `Interview`
- `Offer`
- `Placement`
- `Fee`
- `Activity`
- `AuditLog`
- `Task`
- `Note`

`CandidateSubmission` is an independent aggregate. A candidate can have
multiple submissions to different clients and mandates. Submission creation
and status changes produce Activity records.

The recruiting flow is:

```text
Candidate -> CandidateSubmission/CV-Out -> Feedback -> Interview
          -> Offer -> Placement -> Fee
```

Submission status changes use the dedicated endpoint
`PATCH /api/v1/submissions/{id}/transition`. Arbitrary status updates through
the general CRUD endpoint are not allowed.

## Current API

All business endpoints are under `/api/v1`.

| Resource | Endpoints |
| --- | --- |
| Health | `GET /health` |
| Candidates | `GET`, `POST /candidates`; `GET`, `PATCH`, `DELETE /candidates/{id}` |
| Candidate submissions | `GET /candidates/{id}/submissions` |
| Clients | `GET`, `POST /clients`; `GET`, `PATCH`, `DELETE /clients/{id}` |
| Contacts | `GET`, `POST /contacts`; `GET`, `PATCH`, `DELETE /contacts/{id}` |
| Jobs | `GET`, `POST /jobs`; `GET`, `PATCH`, `DELETE /jobs/{id}` |
| Submissions | `GET`, `POST /submissions`; `GET`, `PATCH`, `DELETE /submissions/{id}` |
| Submission transitions | `PATCH /submissions/{id}/transition` |
| Feedback | `GET`, `POST /submissions/{id}/feedback`; `GET /feedback` |
| Interviews | `GET`, `POST /submissions/{id}/interviews`; `GET /interviews` |
| Offers | `GET`, `POST /submissions/{id}/offers`; `GET /offers` |
| Placements | `GET`, `POST /submissions/{id}/placement`; `GET /placements` |
| Fees | `GET /fees`; `POST /placements/{id}/fees` |
| Audit | `GET /audit-logs` |
| Activities | `GET`, `POST /activities`; `GET`, `PATCH`, `DELETE /activities/{id}` |
| Tasks | `GET`, `POST /tasks`; `GET`, `PATCH`, `DELETE /tasks/{id}` |
| Notes | `GET`, `POST /notes`; `GET`, `PATCH`, `DELETE /notes/{id}` |

## Layering

- `api`: HTTP parsing, response schemas, and error mapping
- `schemas`: Pydantic API contracts
- `services`: transactions and business rules
- `repositories`: SQLAlchemy persistence
- `models`: relational data model
- `core`: configuration and shared errors
- `integrations`: provider-specific adapters behind application ports

Business rules must not be added directly to API route functions.

Candidate, client, job, and submission list endpoints support stable
`limit`/`offset` pagination and return `items`, `total_count`, `limit`, and
`offset`. They also expose simple status, region, role, relationship, date, and
text filters where applicable.
