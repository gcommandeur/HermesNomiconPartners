# NOMICON: Demo-Login ohne Passwort und ohne 2FA - nur lokal, nur zwei feste Demo-Konten.
"""ACHTUNG: Das ist eine bewusste Umgehung der Anmeldung. Schutzmassnahmen (alle muessen gelten):

1. Schalter `CC_CRM_DEMO_LOGIN` (Standard aus).
2. Wirkt nur in der Umgebung `local`, `test` oder `demo` UND bei SQLite oder einem Postgres auf
   localhost. In jeder anderen Umgebung beendet sich die App beim Start mit Fehlermeldung, wenn der
   Schalter an ist (`assert_demo_login_safe`, aus dem Lifespan aufgerufen).
3. Der Endpunkt meldet ausschliesslich die zwei hier fest definierten Konten an (Adressen auf
   `.local`), nie ein anderes Konto; ohne Schalter oder in unsicherer Umgebung: 404.
4. Die Konten bekommen beim Seed ein zufaelliges, nie ausgegebenes Passwort; normaler Login bleibt
   dadurch unmoeglich."""

import secrets
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.config import Settings
from cc_crm.core.security import hash_password
from cc_crm.models.access_views import UserViewAccess, UserViewSettings
from cc_crm.models.user import User

SAFE_ENVIRONMENTS = frozenset({"local", "test", "demo"})
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True)
class DemoPersona:
    key: str
    email: str
    display_name: str
    role: str
    views: tuple[str, ...]
    default_view: str


DEMO_PERSONAS: dict[str, DemoPersona] = {
    "admin": DemoPersona(
        "admin",
        "demo-admin@nomicon.local",
        "Demo Admin",
        "admin",
        ("direct", "staffing", "management"),
        "management",
    ),
    "vermittler": DemoPersona(
        "vermittler",
        "demo-vermittler@nomicon.local",
        "Demo Vermittler",
        "member",
        ("direct", "staffing"),  # fuer den Test beides sichtbar; der Admin kann es entziehen
        "direct",
    ),
}


def database_is_local(database_url: str) -> bool:
    """SQLite (Datei oder Speicher) oder Postgres auf localhost - nie ein fremder Host."""
    if database_url.startswith("sqlite"):
        return True
    host = urlparse(database_url).hostname
    return host in LOCAL_HOSTS


def demo_login_problem(settings: Settings) -> str | None:
    """Warum der Demo-Login hier NICHT laufen darf (None = unproblematisch oder ausgeschaltet)."""
    if not settings.demo_login:
        return None
    if settings.environment not in SAFE_ENVIRONMENTS:
        return (
            f"CC_CRM_DEMO_LOGIN ist an, aber die Umgebung ist '{settings.environment}' "
            f"(erlaubt: {', '.join(sorted(SAFE_ENVIRONMENTS))})."
        )
    if not database_is_local(settings.resolved_database_url):
        return (
            "CC_CRM_DEMO_LOGIN ist an, aber die Datenbank ist weder SQLite noch ein "
            "localhost-Postgres."
        )
    return None


def assert_demo_login_safe(settings: Settings) -> None:
    """Beim App-Start: unsichere Kombination = Abbruch mit klarer Meldung."""
    problem = demo_login_problem(settings)
    if problem is not None:
        raise RuntimeError(
            f"{problem} Der Demo-Login umgeht die Anmeldung und darf nur lokal laufen. "
            "App wird nicht gestartet."
        )


def demo_login_active(settings: Settings) -> bool:
    return settings.demo_login and demo_login_problem(settings) is None


def ensure_demo_users(session: Session) -> list[User]:
    """Legt die zwei Demo-Konten an (idempotent). Bestehende Konten und spaeter vom Demo-Admin
    geaenderte Ansichten bleiben unveraendert; das Passwort ist zufaellig, nie ausgegeben."""
    users: list[User] = []
    for persona in DEMO_PERSONAS.values():
        user = session.scalar(select(User).where(User.email == persona.email))
        if user is None:
            user = User(
                email=persona.email,
                hashed_password=hash_password(secrets.token_urlsafe(32)),
                display_name=persona.display_name,
                role=persona.role,
                is_active=True,
            )
            session.add(user)
            session.flush()
            for view in persona.views:
                session.add(UserViewAccess(user_id=user.id, view=view))
            session.add(UserViewSettings(user_id=user.id, default_view=persona.default_view))
        users.append(user)
    session.commit()
    return users
