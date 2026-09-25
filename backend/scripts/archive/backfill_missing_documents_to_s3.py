"""Laedt Dokumente, die in der Produktions-Datenbank referenziert sind, aber
im Produktions-Bucket fehlen, aus dem lokalen Dateibestand
(`backend/data/documents/`) nach.

Hintergrund: `CC_CRM_S3_ENDPOINT_URL` war in Produktion auf die bucket-
spezifische Adresse gesetzt (Bucket-Name im Host UND als Parameter -> jeder
S3-Aufruf schlug fehl, siehe core/config.py::_strip_bucket_prefix_from_s3_endpoint).
Nach der Reparatur war live bestaetigt: der Produktions-Bucket ist komplett
leer (0 Objekte) - alle 2482 referenzierten Kandidaten-Dokumente fehlen im
Bucket, nicht nur ein historischer Teil.

Braucht KEINEN Zugriff auf die Produktions-Datenbank - der storage_key aus
`scripts/audit_document_storage.py --check-bucket` (in der Produktions-
Console gegen die echte DB gelaufen) codiert bereits vollstaendig
"owner_type/owner_id/dateiname" und wird 1:1 als S3-Objektschluessel
wiederverwendet, ohne die DB erneut abzufragen. Braucht dafuer ECHTE
Produktions-S3-Zugangsdaten in der lokalen `.env` (CC_CRM_S3_BUCKET,
CC_CRM_S3_ENDPOINT_URL, CC_CRM_S3_REGION, CC_CRM_S3_ACCESS_KEY_ID,
CC_CRM_S3_SECRET_ACCESS_KEY) - die traegt der Nutzer selbst ein, siehe
Chat-Verlauf.

Dry-Run per Default (zeigt nur, was hochgeladen wuerde) - --apply fuer den
echten Schreiblauf.

Usage (aus backend/, mit lokal eingetragenen Produktions-S3-Zugangsdaten):

    python scripts/backfill_missing_documents_to_s3.py missing_in_bucket.txt
    python scripts/backfill_missing_documents_to_s3.py missing_in_bucket.txt --apply

`missing_in_bucket.txt` = die storage_key-Liste aus
`audit_document_storage.py --check-bucket` (eine Zeile pro storage_key,
exakt wie ausgegeben, siehe dortiger Docstring).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from cc_crm.core.config import get_settings  # noqa: E402
from cc_crm.services.storage import _s3_client, document_exists  # noqa: E402


def _read_storage_keys(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def backfill(*, keys_file: Path, apply: bool) -> dict[str, int]:
    settings = get_settings()
    if not settings.s3_bucket:
        print(
            "FEHLER: CC_CRM_S3_BUCKET ist lokal nicht gesetzt - bitte zuerst die "
            "Produktions-S3-Zugangsdaten in backend/.env eintragen (siehe Skript-Docstring)."
        )
        raise SystemExit(1)

    storage_keys = _read_storage_keys(keys_file)
    print(f"Zu prüfende storage_keys aus '{keys_file}': {len(storage_keys)}")
    print(f"Ziel-Bucket: {settings.s3_bucket} ({settings.s3_endpoint_url})\n")

    local_root = settings.resolved_documents_storage_dir
    client = _s3_client()

    would_upload: list[tuple[str, Path, int]] = []
    missing_locally: list[str] = []
    already_present: list[str] = []

    for storage_key in storage_keys:
        local_path = local_root / storage_key
        if not local_path.is_file():
            missing_locally.append(storage_key)
            continue
        # Erneut prüfen statt der (evtl. veralteten) Eingabe-Liste blind zu
        # vertrauen - falls zwischen Audit-Lauf und diesem Lauf bereits
        # etwas hochgeladen wurde, dieses Objekt nicht nochmal überschreiben.
        if document_exists(storage_key):
            already_present.append(storage_key)
            continue
        would_upload.append((storage_key, local_path, local_path.stat().st_size))

    print(f"Bereits im Bucket vorhanden (übersprungen): {len(already_present)}")
    print(f"Fehlt lokal ebenfalls (nicht reparierbar durch dieses Skript): {len(missing_locally)}")
    for key in missing_locally:
        print(f"  FEHLT LOKAL: {key}")

    print(f"\n{'Wird hochgeladen' if apply else 'Würde hochgeladen werden'}: {len(would_upload)}")
    uploaded = 0
    failed = 0
    for storage_key, local_path, size in would_upload:
        action = "HOCHGELADEN" if apply else "WÜRDE HOCHLADEN"
        print(f"  {action}: {storage_key} ({size:,} Bytes)")
        if apply:
            try:
                content = local_path.read_bytes()
                client.put_object(Bucket=settings.s3_bucket, Key=storage_key, Body=content)
                uploaded += 1
            except Exception as exception:  # noqa: BLE001 - ein Fehlschlag darf den Lauf nicht abbrechen
                failed += 1
                print(f"    FEHLER beim Hochladen von {storage_key}: {exception}")

    return {
        "checked": len(storage_keys),
        "already_present": len(already_present),
        "missing_locally": len(missing_locally),
        "would_upload_or_uploaded": len(would_upload),
        "uploaded": uploaded,
        "failed": failed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "keys_file",
        type=Path,
        help="Datei mit storage_keys (aus audit_document_storage.py --check-bucket)",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Tatsächlich hochladen (Default: Dry-Run)"
    )
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Dokument-Backfill in Produktions-Bucket ({mode}) ===\n")
    stats = backfill(keys_file=args.keys_file, apply=args.apply)

    print("\n=== Zusammenfassung ===")
    for key, value in stats.items():
        print(f"{key}: {value}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde hochgeladen.")
        print("Mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
