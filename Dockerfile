FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/README.md ./backend/
COPY backend/src ./backend/src
RUN pip install --no-cache-dir ./backend

COPY backend/alembic.ini ./backend/
COPY backend/alembic ./backend/alembic
COPY backend/scripts ./backend/scripts
COPY backend/templates ./backend/templates

WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail "http://localhost:${PORT}/api/v1/health" || exit 1

# Migrationen laufen bei jedem Start automatisch (idempotent) - kein manueller
# SSH-Schritt nötig, wenn ein neues Image deployt wird. Mit
# CC_CRM_MIGRATE_ON_STARTUP=false (siehe docs/DEPLOYMENT.md, Abschnitt "Betrieb")
# entfällt das hier UND im App-Start; die Migration läuft dann als eigener
# Pre-Deploy-Job. Standard ohne die Variable: wie bisher.
CMD ["sh", "-c", "if [ \"${CC_CRM_MIGRATE_ON_STARTUP:-true}\" != \"false\" ]; then alembic upgrade head; fi && exec uvicorn cc_crm.main:app --app-dir src --host 0.0.0.0 --port ${PORT}"]
