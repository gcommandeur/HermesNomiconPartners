from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_copies_templates_directory() -> None:
    """Regressionsschutz: profile_docx_export.py laedt die Word-Mastervorlage
    zur Laufzeit ueber einen relativen Pfad (backend/templates/...) - wenn das
    root-Dockerfile dieses Verzeichnis nicht mit ins Image kopiert, existiert
    die Datei im Produktions-Container schlicht nicht und der Word-Export
    schlaegt mit 500 fehl, obwohl lokal (wo das Repo direkt vorliegt) alles
    funktioniert. Dieser Test waere durchgefallen, bevor `COPY backend/templates
    ./backend/templates` ergaenzt wurde."""
    dockerfile = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY backend/templates" in dockerfile


def test_master_profile_template_exists_in_repo() -> None:
    template = _REPO_ROOT / "backend" / "templates" / "anonymes_profil_master.docx"
    assert template.is_file()
