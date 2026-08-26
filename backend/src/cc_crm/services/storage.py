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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

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


def _safe_type_segment(document_type: str) -> str:
    """Nur alphanumerische Zeichen fuer den Dateinamen-Zusatz - document_type
    ist ein freies String-Feld (siehe models/operational.py), keine
    Enum-Garantie auf "sichere" Zeichen."""
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in document_type.lower())
    return cleaned.strip("_") or "dokument"


class _NamedDocument(Protocol):
    """Strukturelle Typisierung statt eines Imports von models.operational.Document
    - so kann diese Funktion sowohl mit echten ORM-Objekten (Bulk-Umbenennung,
    siehe scripts/rename_documents_to_candidate_number.py) als auch mit einem
    noch nicht in der DB existierenden, synthetischen Eintrag fuer einen
    GERADE laufenden Upload aufgerufen werden (siehe
    api/v1/operational.py::upload_document)."""

    id: uuid.UUID
    document_type: str
    filename: str
    created_at: datetime


def candidate_document_filenames(
    documents: list[_NamedDocument], candidate_number: str
) -> dict[uuid.UUID, str]:
    """Bestimmt fuer ALLE Dokumente eines Kandidaten (nicht nur eines
    einzelnen) den Ziel-Dateinamen nach der Kandidaten-Nr.-Konvention (Nutzer-
    Vorgabe: Dateiname soll nur noch die Kandidaten-Nr. sein, z.B. "1823.pdf"
    statt "ddd4ce82_1823_Kroll_Simon.pdf" - bei mehreren Dokumenten desselben
    Kandidaten zusaetzlich ein Dokumenttyp-Zusatz, bei mehreren Dokumenten
    DESSELBEN Typs zusaetzlich eine fortlaufende Nummer nach Upload-Datum
    sortiert, um Kollisionen zu vermeiden - live auf Produktion bestaetigter
    Fall: Kandidat 1823/Simon Kroll hatte durch einen Re-Upload zwei
    CV-Dokumente).

    Gemeinsam genutzt von der Bulk-Umbenennung bestehender Dokumente
    (scripts/rename_documents_to_candidate_number.py) UND vom Upload-
    Endpunkt fuer neue Dokumente, damit beide garantiert dieselbe Konvention
    anwenden und nicht auseinanderlaufen."""
    if len(documents) == 1:
        document = documents[0]
        ext = Path(document.filename).suffix.lower()
        return {document.id: f"{candidate_number}{ext}"}

    def _sort_key(document: _NamedDocument) -> datetime:
        # SQLite gibt fuer DateTime(timezone=True)-Spalten beim Lesen naive
        # datetimes zurueck (kein echtes tz-aware Storage) - ein frisch per
        # datetime.now(UTC) gebauter synthetischer Eintrag (siehe
        # plan_new_candidate_document) ist dagegen tz-aware. Ohne diese
        # Normalisierung wirft sorted() TypeError beim Vergleich von naiven
        # und tz-aware datetimes.
        timestamp = document.created_at
        return timestamp.replace(tzinfo=None) if timestamp.tzinfo is not None else timestamp

    by_type: dict[str, list[_NamedDocument]] = {}
    for document in sorted(documents, key=_sort_key):
        by_type.setdefault(document.document_type, []).append(document)

    result: dict[uuid.UUID, str] = {}
    for document_type, type_documents in by_type.items():
        type_segment = _safe_type_segment(document_type)
        for index, document in enumerate(type_documents, start=1):
            ext = Path(document.filename).suffix.lower()
            suffix = "" if index == 1 else f"_{index}"
            result[document.id] = f"{candidate_number}_{type_segment}{suffix}{ext}"
    return result


@dataclass
class _VirtualDocument:
    """Steht fuer ein GERADE hochgeladenes Dokument, das noch keine DB-Zeile
    (und damit noch keine echte id) hat - siehe plan_new_candidate_document."""

    id: uuid.UUID
    document_type: str
    filename: str
    created_at: datetime


def plan_new_candidate_document(
    existing_documents: list[_NamedDocument],
    candidate_number: str,
    document_type: str,
    filename: str,
) -> tuple[str, dict[uuid.UUID, str]]:
    """Bestimmt den Dateinamen fuer ein GERADE hochzuladenes Kandidaten-
    Dokument nach der Kandidaten-Nr.-Konvention, sowie ggf. noetige
    Umbenennungen bereits vorhandener Geschwister-Dokumente desselben
    Kandidaten (nur relevant, wenn aus einem bisherigen Einzeldokument durch
    diesen Upload ein Mehrfachfall wird - das bisher "nackte"
    Kandidaten-Nr.-Dokument braucht dann nachtraeglich denselben
    Typ-Zusatz wie das neue, um konsistent zu bleiben). Gibt
    (neuer_dateiname_fuer_upload, {bestehendes_document.id: neuer_dateiname})
    zurueck - das zweite Dict ist im weit ueberwiegenden Normalfall (0 oder
    bereits >=2 bestehende, schon typ-benannte Dokumente) leer."""
    new_id = uuid.uuid4()
    virtual_new = _VirtualDocument(
        id=new_id, document_type=document_type, filename=filename, created_at=datetime.now(UTC)
    )
    names = candidate_document_filenames([*existing_documents, virtual_new], candidate_number)
    new_filename = names.pop(new_id)
    sibling_renames = {
        document.id: names[document.id]
        for document in existing_documents
        if names.get(document.id) not in (None, document.filename)
    }
    return new_filename, sibling_renames


# Umlaut-/Sonderzeichen-Transkription fuer Dateinamen (siehe
# cv_upload_filename unten) - dieselbe ae/oe/ue/ss-Konvention wie an anderen
# Normalisierungsstellen im Projekt (z.B. repositories/candidates.py fuer die
# Freitextsuche), hier aber fuer einen DATEINAMEN statt einen SQL-Vergleich.
_UMLAUT_TRANSLITERATION = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
}
_INVALID_FILENAME_CHARS_RE = re.compile(r"[^A-Za-z0-9\-]")
_MULTI_HYPHEN_RE = re.compile(r"-{2,}")


def _normalize_name_part_for_filename(value: str) -> str:
    """Ein Namensteil (Vor- oder Nachname) fuer die CV_NACHNAME.VORNAME-
    Konvention (siehe cv_upload_filename): Umlaute transkribiert, Leerzeichen
    (Doppelnamen wie "von der Heide") zu Bindestrich statt abgeschnitten,
    bereits vorhandene Bindestriche (Doppelnamen wie "Müller-Lüdenscheid")
    bleiben erhalten - alles andere entfernt statt durch Unterstriche
    ersetzt, damit der Name kompakt bleibt."""
    cleaned = value.strip()
    for umlaut, replacement in _UMLAUT_TRANSLITERATION.items():
        cleaned = cleaned.replace(umlaut, replacement)
    cleaned = re.sub(r"\s+", "-", cleaned)
    cleaned = _INVALID_FILENAME_CHARS_RE.sub("", cleaned)
    cleaned = _MULTI_HYPHEN_RE.sub("-", cleaned).strip("-")
    return cleaned or "Unbekannt"


def cv_upload_filename(
    *, first_name: str, last_name: str, existing_cv_count: int, extension: str
) -> str:
    """CV-Dateinamens-Konvention (Nutzer-Vorgabe): "CV_NACHNAME.VORNAME" +
    Dateiendung, z.B. "CV_MUSTERMANN.MAX.pdf" - GILT NUR fuer document_type
    == "cv" (siehe api/v1/operational.py::_candidate_upload_naming). Andere
    Kandidaten-Dokumenttypen (Vertraege etc.) bleiben bei der bestehenden
    Kandidaten-Nr.-Konvention (candidate_document_filenames oben) - diese
    hier ist bewusst NICHT candidate_number-basiert, weil die Konvention
    explizit den Namen im Dateinamen verlangt.

    Bei mehreren CVs derselben Person haengt ab dem ZWEITEN CV ein
    fortlaufender Zaehler an (z.B. "CV_MUSTERMANN.MAX_2.pdf") -
    `existing_cv_count` ist die Anzahl der VOR diesem Upload bereits
    vorhandenen CV-Dokumente desselben Kandidaten."""
    last = _normalize_name_part_for_filename(last_name)
    first = _normalize_name_part_for_filename(first_name)
    base = f"CV_{last}.{first}"
    suffix = "" if existing_cv_count == 0 else f"_{existing_cv_count + 1}"
    ext = extension if extension.startswith(".") else f".{extension}"
    return f"{base}{suffix}{ext}"


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
    *,
    owner_type: str,
    owner_id: uuid.UUID,
    filename: str,
    content: bytes,
    storage_key: str | None = None,
) -> str:
    """Speichert die Bytes und gibt den storage_key zurück. Ohne `storage_key`
    (Standardfall) wird ein zufälliger, kollisionssicherer Schlüssel gebaut
    ("owner_type/owner_id/uuid_datei") - für Kandidaten-Dokumente mit
    bekannter Kandidaten-Nr. übergibt der Aufrufer stattdessen den bereits
    nach der Kandidaten-Nr.-Konvention berechneten Ziel-Schlüssel (siehe
    candidate_document_filenames), damit die Datei direkt unter ihrem
    endgültigen Namen landet statt über einen Zwischen-Umbenennungsschritt."""
    storage_key = storage_key or _storage_key_for(owner_type, owner_id, filename)

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
        from botocore.exceptions import ClientError  # lazy - siehe _s3_client()

        settings = get_settings()
        assert settings.s3_bucket is not None
        try:
            response = _s3_client().get_object(Bucket=settings.s3_bucket, Key=storage_key)
        except ClientError as exc:
            # Ein Dokument, dessen DB-Zeile existiert, aber dessen Objekt im
            # Bucket fehlt (z.B. bei einer Migration mitgenommene Zeilen ohne
            # zugehoerigen Datei-Upload) - vereinheitlicht mit dem lokalen
            # Backend, das fuer denselben Fall FileNotFoundError wirft (siehe
            # unten), damit beide Aufrufer (Download-Endpoint,
            # profile_generator.py::_cv_text_for_candidate) EINEN
            # Exception-Typ behandeln muessen, nicht zwei parallele.
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in {"NoSuchKey", "404"}:
                raise FileNotFoundError(
                    f"Objekt nicht im Speicher gefunden: {storage_key}"
                ) from exc
            raise
        return bytes(response["Body"].read())

    return (_local_storage_root() / storage_key).read_bytes()


def rename_document_bytes(*, old_storage_key: str, new_storage_key: str) -> None:
    """Verschiebt ein Objekt auf einen neuen storage_key (Kopie auf den neuen
    Schlüssel, per document_exists verifiziert, danach das alte Objekt
    gelöscht) - bei einem Abbruch mittendrin geht dadurch nie eine Datei
    komplett verloren (im schlimmsten Fall existiert sie kurzzeitig doppelt).
    Gemeinsam genutzt von der Bulk-Umbenennung (scripts/
    rename_documents_to_candidate_number.py) und vom Upload-Endpunkt (wenn
    ein neuer Upload ein bestehendes Geschwister-Dokument umbenennen muss,
    siehe candidate_document_filenames)."""
    if old_storage_key == new_storage_key:
        return

    if _s3_configured():
        settings = get_settings()
        assert settings.s3_bucket is not None
        _s3_client().copy_object(
            Bucket=settings.s3_bucket,
            CopySource={"Bucket": settings.s3_bucket, "Key": old_storage_key},
            Key=new_storage_key,
        )
        if not document_exists(new_storage_key):
            raise RuntimeError(
                f"Kopie nach copy_object nicht per head_object bestätigt: {new_storage_key}"
            )
        delete_document_bytes(old_storage_key)
        return

    old_path = _local_storage_root() / old_storage_key
    new_path = _local_storage_root() / new_storage_key
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_bytes(old_path.read_bytes())
    old_path.unlink()


def delete_document_bytes(storage_key: str) -> None:
    """Loescht die Datei unwiderruflich aus dem aktiven Backend - u.a. Basis
    fuer die Kandidaten-Anonymisierung (services/candidates.py::anonymize),
    wo CV-Dokumente tatsaechlich aus dem Speicher entfernt werden muessen,
    nicht nur ihre Metadaten aus der DB. Ein bereits fehlendes Objekt ist
    kein Fehler (idempotent - z.B. bei wiederholtem Aufruf)."""
    if _s3_configured():
        settings = get_settings()
        assert settings.s3_bucket is not None
        _s3_client().delete_object(Bucket=settings.s3_bucket, Key=storage_key)
        return

    path = _local_storage_root() / storage_key
    path.unlink(missing_ok=True)


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
