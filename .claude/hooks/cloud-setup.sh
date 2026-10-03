#!/usr/bin/env bash
# Wird beim Start einer Claude-Code-Sitzung ausgefuehrt (siehe
# .claude/settings.json, Hook SessionStart) - aber NUR in der Cloud
# (CLAUDE_CODE_REMOTE=true), nie auf dem lokalen Rechner. Installiert die
# Abhaengigkeiten, damit pytest/ruff/mypy und pnpm lint/typecheck/build ohne
# Handarbeit laufen (z.B. wenn die Sitzung vom Handy aus gestartet wurde).
# Idempotent und fehlertolerant: ein Fehler hier darf die Sitzung nicht blockieren.
set -u

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$ROOT" || exit 0

if [ -f backend/pyproject.toml ]; then
  echo "[cloud-setup] Backend-Abhaengigkeiten ..."
  # Das Backend braucht Python >= 3.12; python3 ist in der Cloud 3.11.
  PY=""
  for candidate in python3.13 python3.12; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
  done
  if [ -z "$PY" ]; then
    echo "[cloud-setup] WARNUNG: weder python3.13 noch python3.12 gefunden"
  else
    (cd backend && { [ -x .venv/bin/python ] || "$PY" -m venv .venv; } \
      && .venv/bin/python -m pip install --quiet -e ".[dev]") \
      || echo "[cloud-setup] WARNUNG: Backend-Installation fehlgeschlagen"
  fi
  # pytest/ruff/mypy/alembic ohne Pfad aufrufbar machen; Tests brauchen
  # ausserdem eine SQLite-URL, sonst versucht die App Postgres auf localhost.
  if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    {
      echo "export PATH=\"$ROOT/backend/.venv/bin:\$PATH\""
      echo "export CC_CRM_DATABASE_URL=\"sqlite:////tmp/cc_crm_test.db\""
    } >> "$CLAUDE_ENV_FILE"
  fi
fi

if [ -f frontend/package.json ]; then
  echo "[cloud-setup] Frontend-Abhaengigkeiten ..."
  # Gleiche pnpm-Version wie CI (.github/workflows/ci.yml).
  command -v pnpm >/dev/null 2>&1 || corepack enable >/dev/null 2>&1 || true
  (cd frontend && pnpm install --frozen-lockfile --silent) \
    || echo "[cloud-setup] WARNUNG: pnpm install fehlgeschlagen"
fi

exit 0
