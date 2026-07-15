"""Datei-Speicher für Dokumente (CVs, Verträge, etc.) - zwei Backends:

1. Lokaler Ordner (Standard, für lokale Entwicklung): Dateien landen unter
   `Settings.documents_storage_dir`, sortiert nach owner_type/owner_id.
2. S3-kompatibler Objektspeicher (Cloudflare R2, AWS S3, Backblaze B2, ...):
   wird automatisch verwendet, sobald `CC_CRM_S3_BUCKET` gesetzt ist. Wichtig
   für produktiven Betrieb/Hosting - die meisten Hosting-Plattformen löschen
   lokale Dateien bei jedem Deploy/Neustart, ein Objektspeicher übersteht das.

Beide Backends teilen sich dieselbe öffentliche Schnittstelle
(save_document_bytes/read_document_bytes/document_exists) und denselben
storage_key-Formatstring ("owner_type/owner_id/uuid_dateiname") - der Rest der
App (Document-Modell, API-Endpunkte) muss nicht wissen, welches Backend aktiv
ist.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from cc_crm.core.config import get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def _safe_filename(filename: str) -> str:
    """Entfernt Pfadanteile und exotische Zeichen, behält Umlaute/Leerzeichen."""
    name = Path(filename).name
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    return name.strip() or "datei"


# Generische CV-Dateinamen: das Schlagwort, danach NUR optionale Zahlen,
# Klammern oder Leerzeichen (z.B. "CV.pdf", "resume (2).pdf",
# "Lebenslauf1.docx") - NICHT bei "lebenslauf-hans-mueller.pdf", da dort nach
# dem Schlagwort weitere Buchstaben folgen.
_GENERIC_FILENAME_RE = re.compile(r"^(resume|bewerbung|cv|lebenslauf)[\d\s()]*$", re.IGNORECASE)


def has_generic_filename(filename: str) -> bool:
    """True, wenn der Dateiname (ohne Endung) einem generischen Muster
    entspricht - Basis fuer den Hinweis-Badge auf Kandidat-Detailseite/Liste."""
    stem = Path(filename).stem.strip()
    return bool(_GENERIC_FILENAME_RE.match(stem))


def _storage_key_for(owner_type: str, owner_id: uuid.UUID, filename: str) -> str:
    safe_name = _safe_filename(filename)
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    return f"{owner_type}/{owner_id}/{unique_name}"


def _s3_configured() -> bool:
    return bool(get_settings().s3_bucket)


def _s3_client() -> S3Client:
    import boto3  # lazy import - nur nötig, wenn S3 tatsächlich konfiguriert ist

    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    )


def _local_storage_root() -> Path:
    root = get_settings().resolved_documents_storage_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_document_bytes(
    *, owner_type: str, owner_id: uuid.UUID, filename: str, content: bytes
) -> str:
    """Speichert die Bytes und gibt den storage_key zurück (Pfad/Objektschlüssel,
    unabhängig vom Backend identisch aufgebaut: "owner_type/owner_id/uuid_datei")."""
    storage_key = _storage_key_for(owner_type, owner_id, filename)

    if _s3_configured():
        settings = get_settings()
        assert settings.s3_bucket is not None
        _s3_client().put_object(Bucket=settings.s3_bucket, Key=storage_key, Body=content)
        return storage_key

    target_path = _local_storage_root() / storage_key
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)
    return storage_key


def read_document_bytes(storage_key: str) -> bytes:
    if _s3_configured():
        settings = get_settings()
        assert settings.s3_bucket is not None
        response = _s3_client().get_object(Bucket=settings.s3_bucket, Key=storage_key)
        return bytes(response["Body"].read())

    return (_local_storage_root() / storage_key).read_bytes()


def document_exists(storage_key: str) -> bool:
    if _s3_configured():
        settings = get_settings()
        assert settings.s3_bucket is not None
        try:
            _s3_client().head_object(Bucket=settings.s3_bucket, Key=storage_key)
            return True
        except Exception:  # noqa: BLE001 - boto3 wirft diverse Fehlerklassen (404 etc.)
            return False

    return (_local_storage_root() / storage_key).is_file()
