"""Tests fuer die Fernet-Ver-/Entschluesselung der Postfach-Passwoerter.

Kernanforderung (Nutzer-Vorgabe): Passwoerter liegen NIE im Klartext in der
Datenbank, und ein fehlender/falscher Schluessel fuehrt zu einem klaren
Fehler statt zu einem stillen Klartext-Fallback.
"""

import pytest
from cryptography.fernet import Fernet

from cc_crm.core.config import Settings
from cc_crm.services.mail_credentials import (
    MailCredentialsError,
    decrypt_password,
    encrypt_password,
)


def _settings_with_key(key: str | None) -> Settings:
    return Settings(mail_credentials_encryption_key=key)


class TestRoundTrip:
    def test_encrypt_then_decrypt_returns_original(self) -> None:
        settings = _settings_with_key(Fernet.generate_key().decode())
        secret = "s3hr-geheim!äöü"

        ciphertext = encrypt_password(secret, settings)

        assert decrypt_password(ciphertext, settings) == secret

    def test_ciphertext_does_not_contain_plaintext(self) -> None:
        """Kernpunkt: das gespeicherte Feld darf das Passwort nicht im
        Klartext enthalten."""
        settings = _settings_with_key(Fernet.generate_key().decode())

        ciphertext = encrypt_password("MeinPasswort123", settings)

        assert "MeinPasswort123" not in ciphertext

    def test_same_password_yields_different_ciphertexts(self) -> None:
        """Fernet nutzt einen Zufalls-IV - zwei Postfaecher mit demselben
        Passwort duerfen in der DB nicht identisch aussehen."""
        settings = _settings_with_key(Fernet.generate_key().decode())

        first = encrypt_password("gleich", settings)
        second = encrypt_password("gleich", settings)

        assert first != second
        assert decrypt_password(first, settings) == decrypt_password(second, settings)


class TestMissingOrWrongKey:
    def test_missing_key_raises_instead_of_storing_plaintext(self) -> None:
        with pytest.raises(MailCredentialsError, match="nicht konfiguriert"):
            encrypt_password("geheim", _settings_with_key(None))

    def test_invalid_key_raises_clear_error(self) -> None:
        with pytest.raises(MailCredentialsError, match="gültiger Fernet-Schlüssel"):
            encrypt_password("geheim", _settings_with_key("das-ist-kein-fernet-key"))

    def test_decrypt_with_different_key_raises(self) -> None:
        """Wurde der Schluessel nachtraeglich getauscht, sind alle
        gespeicherten Passwoerter unlesbar - das muss als klarer Fehler
        sichtbar werden, nicht als leeres Passwort."""
        ciphertext = encrypt_password("geheim", _settings_with_key(Fernet.generate_key().decode()))
        other_settings = _settings_with_key(Fernet.generate_key().decode())

        with pytest.raises(MailCredentialsError, match="nicht entschlüsselt"):
            decrypt_password(ciphertext, other_settings)

    def test_empty_password_is_rejected(self) -> None:
        settings = _settings_with_key(Fernet.generate_key().decode())

        with pytest.raises(MailCredentialsError, match="leeres Postfach-Passwort"):
            encrypt_password("", settings)
