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

WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail "http://localhost:${PORT}/api/v1/health" || exit 1

# Migrationen laufen bei jedem Start automatisch (idempotent) - kein manueller
# SSH-Schritt nötig, wenn ein neues Image deployt wird.
CMD ["sh", "-c", "alembic upgrade head && uvicorn cc_crm.main:app --app-dir src --host 0.0.0.0 --port ${PORT}"]
