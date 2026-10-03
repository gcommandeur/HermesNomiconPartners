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
  (cd backend && python3 -m pip install --quiet -e ".[dev]") \
    || echo "[cloud-setup] WARNUNG: pip install fehlgeschlagen"
fi

if [ -f frontend/package.json ]; then
  echo "[cloud-setup] Frontend-Abhaengigkeiten ..."
  # Gleiche pnpm-Version wie CI (.github/workflows/ci.yml).
  command -v pnpm >/dev/null 2>&1 || corepack enable >/dev/null 2>&1 || true
  (cd frontend && pnpm install --frozen-lockfile --silent) \
    || echo "[cloud-setup] WARNUNG: pnpm install fehlgeschlagen"
fi

exit 0
