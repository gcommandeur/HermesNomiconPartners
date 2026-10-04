"""Verbindungstest fuer IMAP/SMTP-Zugangsdaten, ohne Mail zu senden oder zu lesen.

Nur Login: IMAP anmelden und abmelden, SMTP anmelden und beenden. Die Verbinder
sind austauschbar (Tests). Fehlertexte werden um das Passwort bereinigt, bevor sie
das Backend verlassen (manche Bibliotheken zitieren den LOGIN-Befehl)."""

from __future__ import annotations

import contextlib
import imaplib
import smtplib
from collections.abc import Callable
from dataclasses import dataclass

from cc_crm.schemas.mail import MailConnectionTestResult

TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class MailCredentials:
    imap_host: str
    imap_port: int
    imap_use_ssl: bool
    smtp_host: str
    smtp_port: int
    smtp_use_ssl: bool
    username: str
    password: str


def _imap_login(credentials: MailCredentials) -> None:
    client_class = imaplib.IMAP4_SSL if credentials.imap_use_ssl else imaplib.IMAP4
    client = client_class(credentials.imap_host, credentials.imap_port, timeout=TIMEOUT_SECONDS)
    try:
        client.login(credentials.username, credentials.password)
    finally:
        with contextlib.suppress(imaplib.IMAP4.error, OSError):
            client.logout()


def _smtp_login(credentials: MailCredentials) -> None:
    if credentials.smtp_use_ssl:
        with smtplib.SMTP_SSL(
            credentials.smtp_host, credentials.smtp_port, timeout=TIMEOUT_SECONDS
        ) as smtp:
            smtp.login(credentials.username, credentials.password)
    else:
        with smtplib.SMTP(
            credentials.smtp_host, credentials.smtp_port, timeout=TIMEOUT_SECONDS
        ) as smtp:
            smtp.starttls()
            smtp.login(credentials.username, credentials.password)


def _clean(exc: BaseException, password: str) -> str:
    text = f"{type(exc).__name__}: {exc}"
    if password:
        text = text.replace(password, "***")
    return text[:300]


def check_connection(
    credentials: MailCredentials,
    *,
    imap_connector: Callable[[MailCredentials], None] = _imap_login,
    smtp_connector: Callable[[MailCredentials], None] = _smtp_login,
) -> MailConnectionTestResult:
    imap_error: str | None = None
    smtp_error: str | None = None
    try:
        imap_connector(credentials)
    except Exception as exc:  # noqa: BLE001 - jeder Verbindungsfehler wird gemeldet
        imap_error = _clean(exc, credentials.password)
    try:
        smtp_connector(credentials)
    except Exception as exc:  # noqa: BLE001
        smtp_error = _clean(exc, credentials.password)
    return MailConnectionTestResult(
        imap_ok=imap_error is None,
        imap_error=imap_error,
        smtp_ok=smtp_error is None,
        smtp_error=smtp_error,
    )
