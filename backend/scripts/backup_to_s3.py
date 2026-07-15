"""Sichert die aktuelle SQLite-Datei (Pfad aus CC_CRM_DATABASE_URL) mit
Zeitstempel im Dateinamen in den konfigurierten S3/R2-Bucket - denselben
CC_CRM_S3_*-Umgebungsvariablen wie beim Dokumentenspeicher (services/
storage.py), aber unter einem eigenen "backups/"-Prefix im selben Bucket, um
keinen zweiten Bucket einrichten zu muessen.

Hintergrund: aktuell gibt es kein automatisiertes DB-Backup - in Produktion
mit echten Kandidaten-/Kanzleidaten ein Risiko (siehe docs/DEPLOYMENT.md).
Dieses Skript ist bewusst NUR der Upload-Baustein - kein Cronjob/Scheduler
wird hier eingerichtet, das haengt vom gewaehlten Hosting-Anbieter ab (siehe
Hinweis in docs/DEPLOYMENT.md, z.B. Railway Cron Job).

Voraussetzungen:
  - CC_CRM_DATABASE_URL zeigt auf eine lokale SQLite-Datei
    ("sqlite:///pfad/zur/datei.db") - Postgres o.ae. wird bewusst nicht
    unterstuetzt (kein einzelner Datei-Upload sinnvoll fuer eine laufende
    Server-DB, dafuer waere pg_dump der richtige Weg, nicht dieses Skript).
  - CC_CRM_S3_BUCKET (und die uebrigen CC_CRM_S3_*-Variablen) sind gesetzt.

Ausfuehren:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\backup_to_s3.py

Testen (sobald echte R2-Zugangsdaten vorliegen): einmal manuell ausfuehren
und im R2/S3-Bucket unter "backups/" pruefen, ob eine neue Datei mit
aktuellem Zeitstempel angekommen ist. Ohne echte Zugangsdaten laesst sich der
Upload selbst nicht end-to-end testen (siehe Bericht) - der Code ist aber
ruff/mypy-sauber und die Pfad-/Fehlerbehandlung ueber
test_backup_to_s3.py separat abgedeckt.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cc_crm.core.config import Settings, get_settings  # noqa: E402

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

SQLITE_PREFIX = "sqlite:///"


class BackupError(Exception):
    pass


def s3_client(settings: Settings) -> S3Client:
    """Eigene, kleine Client-Konstruktion statt Import aus services/storage.py
    - dieses Skript ist bewusst eigenstaendig (siehe Modul-Docstring) und soll
    nicht von internen Implementierungsdetails eines anderen Moduls abhaengen."""
    import boto3  # lazy import - nur noetig, wenn das Skript tatsaechlich laeuft

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    )


def sqlite_db_path(database_url: str) -> Path:
    if not database_url.startswith(SQLITE_PREFIX):
        raise BackupError(
            f"CC_CRM_DATABASE_URL ist keine lokale SQLite-Datei ({database_url!r}) - "
            "dieses Skript unterstuetzt nur sqlite:///... (fuer Postgres waere pg_dump "
            "der richtige Weg, nicht ein Datei-Upload)."
        )
    return Path(database_url.removeprefix(SQLITE_PREFIX))


def backup_object_key(db_path: Path, now: datetime) -> str:
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    return f"backups/{db_path.stem}_{timestamp}{db_path.suffix}"


def run_backup() -> str:
    settings = get_settings()
    if not settings.s3_bucket:
        raise BackupError(
            "CC_CRM_S3_BUCKET ist nicht gesetzt - ohne konfigurierten Bucket kann "
            "kein Backup hochgeladen werden (siehe docs/DEPLOYMENT.md)."
        )

    db_path = sqlite_db_path(settings.resolved_database_url)
    if not db_path.is_file():
        raise BackupError(f"SQLite-Datei nicht gefunden: {db_path}")

    object_key = backup_object_key(db_path, datetime.now(UTC))
    content = db_path.read_bytes()

    s3_client(settings).put_object(Bucket=settings.s3_bucket, Key=object_key, Body=content)
    return object_key


def main() -> None:
    try:
        object_key = run_backup()
    except BackupError as exception:
        print(f"FEHLER: {exception}")
        raise SystemExit(1) from exception

    print(f"Backup hochgeladen: {object_key}")


if __name__ == "__main__":
    main()
