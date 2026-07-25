from cc_crm.core.config import Settings


def test_bucket_specific_s3_endpoint_is_auto_corrected() -> None:
    """Regressionsschutz: live auf Produktion bestaetigt, dass ein bucket-
    spezifischer S3_ENDPOINT_URL (Bucket-Name als Host-Praefix) in Kombination
    mit dem separat uebergebenen Bucket-Parameter in services/storage.py zu
    einer doppelt adressierten, kaputten URL fuehrte - jeder S3-Aufruf schlug
    mit einem irrefuehrenden NoSuchKey fehl, unabhaengig vom tatsaechlichen
    Objekt. Settings korrigiert das jetzt automatisch (siehe
    _strip_bucket_prefix_from_s3_endpoint)."""
    settings = Settings(
        s3_bucket="hermescrm",
        s3_endpoint_url="https://hermescrm.fra1.digitaloceanspaces.com",
    )
    assert settings.s3_endpoint_url == "https://fra1.digitaloceanspaces.com"


def test_regional_s3_endpoint_is_left_unchanged() -> None:
    settings = Settings(
        s3_bucket="hermescrm",
        s3_endpoint_url="https://fra1.digitaloceanspaces.com",
    )
    assert settings.s3_endpoint_url == "https://fra1.digitaloceanspaces.com"


def test_s3_endpoint_without_bucket_configured_is_left_unchanged() -> None:
    settings = Settings(s3_bucket=None, s3_endpoint_url="https://fra1.digitaloceanspaces.com")
    assert settings.s3_endpoint_url == "https://fra1.digitaloceanspaces.com"
